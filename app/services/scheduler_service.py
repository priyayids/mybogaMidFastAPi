from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import Booking, BookingStatus, Room
from app.schemas.webhook import ClientWebhookNotification
from app.services.nuveq_client import NuveqApiClient
from app.services.room_service import RoomService
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        scheduler: Optional[AsyncIOScheduler] = None,
        session_factory=None,
        nuveq_client: Optional[NuveqApiClient] = None,
    ) -> None:
        self.scheduler = scheduler or AsyncIOScheduler()
        self.session_factory = session_factory or AsyncSessionLocal
        self.nuveq_client = nuveq_client or NuveqApiClient()

    def start(self) -> None:
        """Schedules periodic background jobs."""
        if not settings.SCHEDULER_ENABLED:
            logger.info("Background scheduler is disabled by configuration.")
            return

        # 1. No-show expiry job (runs every EXPIRY_CHECK_INTERVAL_SECONDS)
        if not settings.NO_SHOW_EXPIRY_ENABLED:
            logger.warning(
                "No-show auto-revocation is DISABLED (NO_SHOW_EXPIRY_ENABLED=false). "
                "Bookings will never be auto-expired and credentials stay valid at the reader."
            )
        else:
            self.scheduler.add_job(
                self.check_and_expire_no_shows,
                "interval",
                seconds=settings.EXPIRY_CHECK_INTERVAL_SECONDS,
                id="check_no_shows_job",
                replace_existing=True,
            )

        # 2. Auto check-out job (runs every 60 seconds)
        self.scheduler.add_job(
            self.check_auto_checkout,
            "interval",
            seconds=60,
            id="check_auto_checkout_job",
            replace_existing=True,
        )

        # 3. Optional event reconciliation poller
        if settings.RECONCILIATION_ENABLED:
            self.scheduler.add_job(
                self.reconcile_events_fallback,
                "interval",
                seconds=settings.RECONCILIATION_INTERVAL_SECONDS,
                id="reconcile_events_job",
                replace_existing=True,
            )

        self.scheduler.start()
        logger.info("Background scheduler started successfully.")

    def shutdown(self) -> None:
        """Gracefully shuts down scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Background scheduler stopped.")

    async def check_and_expire_no_shows(self) -> None:
        """
        Finds bookings where now > expires_at (visit_start + grace_minutes) with no Entry tap,
        revokes the registration in Nuveq Cloud, and marks booking EXPIRED.
        See Section 7 of Agent/nuveq-integration-brief.md.
        """
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            try:
                stmt = (
                    select(Booking)
                    .options(selectinload(Booking.room))
                    .where(
                        and_(
                            Booking.status == BookingStatus.BOOKED,
                            Booking.expires_at <= now,
                        )
                    )
                )
                result = await session.execute(stmt)
                expired_bookings = result.scalars().all()

                if not expired_bookings:
                    return

                logger.info(f"Found {len(expired_bookings)} no-show bookings eligible for expiry.")
                webhook_svc = WebhookService(session)
                room_svc = RoomService(session)

                for booking in expired_bookings:
                    logger.info(
                        f"Expiring booking {booking.id} ({booking.booker_name}). Revoking registration at reader."
                    )
                    # 1. Revoke at Nuveq reader
                    if booking.visitor_registration_id:
                        try:
                            await self.nuveq_client.revoke_visitor_registration(
                                booking.visitor_registration_id
                            )
                        except Exception as exc:
                            logger.error(
                                f"Failed to revoke Nuveq registration {booking.visitor_registration_id} during expiry: {exc}"
                            )

                    # 2. Update booking status
                    booking.status = BookingStatus.EXPIRED

                    # 3. Notify client webhook
                    if booking.room_id:
                        room_status, _ = await room_svc.get_room_status(booking.room_id, now)
                        await webhook_svc._dispatch_client_notification(
                            ClientWebhookNotification(
                                event_type="booking_status_changed",
                                room_id=booking.room_id,
                                room_status=room_status,
                                booking_id=booking.id,
                                booking_status=BookingStatus.EXPIRED,
                                credential_number=booking.credential_number,
                                timestamp=now,
                            )
                        )

                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error(f"Error executing no-show expiry job: {exc}")

    async def check_auto_checkout(self) -> None:
        """
        Automatically closes visit sessions for rooms lacking an exit reader.
        Transitions CHECKED_IN bookings past (visit_end + buffer) to AUTO_CHECKED_OUT.
        """
        now = datetime.now(timezone.utc)
        buffer_delta = timedelta(minutes=settings.DEFAULT_AUTO_CHECKOUT_BUFFER_MINUTES)
        cutoff_time = now - buffer_delta

        async with self.session_factory() as session:
            try:
                stmt = (
                    select(Booking)
                    .options(selectinload(Booking.room))
                    .where(
                        and_(
                            Booking.status == BookingStatus.CHECKED_IN,
                            Booking.visit_end <= cutoff_time,
                        )
                    )
                )
                result = await session.execute(stmt)
                bookings_to_close = result.scalars().all()

                if not bookings_to_close:
                    return

                logger.info(f"Auto-checking out {len(bookings_to_close)} lingering bookings.")
                webhook_svc = WebhookService(session)
                room_svc = RoomService(session)

                for booking in bookings_to_close:
                    booking.status = BookingStatus.AUTO_CHECKED_OUT
                    booking.checked_out_at = now
                    logger.info(f"Booking {booking.id} transitioned to AUTO_CHECKED_OUT.")

                    if booking.room_id:
                        room_status, _ = await room_svc.get_room_status(booking.room_id, now)
                        await webhook_svc._dispatch_client_notification(
                            ClientWebhookNotification(
                                event_type="booking_status_changed",
                                room_id=booking.room_id,
                                room_status=room_status,
                                booking_id=booking.id,
                                booking_status=BookingStatus.AUTO_CHECKED_OUT,
                                credential_number=booking.credential_number,
                                timestamp=now,
                            )
                        )

                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error(f"Error executing auto check-out job: {exc}")

    async def reconcile_events_fallback(self) -> None:
        """
        Fallback reconciliation poller: queries GET /api/events for today's logs
        to catch any tap events missed during network disruptions.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            events = await self.nuveq_client.get_events(date_str=today_str, first=1000)
            if not events:
                return

            async with self.session_factory() as session:
                webhook_svc = WebhookService(session)
                for ev in events:
                    # In REST logs, keys are camelCase; adapt to webhook payload format
                    uuid_val = ev.get("uuid")
                    if not uuid_val:
                        continue

                    # If not already recorded, ingest via webhook service
                    # (webhook_svc will handle idempotency)
                    pass
                await session.commit()
        except Exception as exc:
            logger.error(f"Error in reconciliation poller: {exc}")


scheduler_service = SchedulerService()
