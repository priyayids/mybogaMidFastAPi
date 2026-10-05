from datetime import datetime, timezone
import json
import logging
from typing import Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Booking,
    BookingStatus,
    ClientWebhookConfig,
    IdempotencyRecord,
    Room,
    TapEvent,
)
from app.schemas.webhook import (
    ClientWebhookNotification,
    NuveqWebhookPayload,
    WebhookAckResponse,
)
from app.services.room_service import RoomService

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.room_service = RoomService(db)

    async def process_nuveq_webhook(self, payload: NuveqWebhookPayload) -> WebhookAckResponse:
        """
        Processes incoming Nuveq event payload.
        Ensures idempotency, records tap event, transitions booking state,
        and broadcasts status updates to client webhook.
        """
        # 1. Idempotency Check
        stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == payload.uuid)
        existing_record = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing_record:
            logger.info(f"Duplicate Nuveq webhook event {payload.uuid} ignored.")
            return WebhookAckResponse(
                received=True,
                uuid=payload.uuid,
                message="Duplicate event ignored",
                processed=False,
            )

        # Record idempotency key immediately
        idempotency_entry = IdempotencyRecord(
            key=payload.uuid,
            category="nuveq_webhook",
            response_json=json.dumps({"name": payload.name, "card_no": payload.card_no}),
        )
        self.db.add(idempotency_entry)

        # 2. Record Raw Tap Event
        tap = TapEvent(
            uuid=payload.uuid,
            mac=payload.mac,
            site_id=payload.site_id,
            door_id=payload.door_id,
            card_no=payload.card_no,
            name=payload.name,
            direction=payload.direction,
            timestamp=payload.timestamp or datetime.now(timezone.utc),
            raw_payload=payload.model_dump_json(),
            processed=False,
        )
        self.db.add(tap)
        await self.db.flush()

        # 3. State Machine Transition for Visitor Taps
        # In Nuveq, visitor taps have name == "Valid visitor" and card_no == booking.credential_number
        if payload.name == "Valid visitor" and payload.card_no and payload.card_no > 0:
            await self._handle_valid_visitor_tap(payload, tap)
        else:
            logger.info(
                f"Non-visitor or status event: '{payload.name}', direction: '{payload.direction}', card_no: {payload.card_no}"
            )
            tap.processed = True

        await self.db.flush()
        return WebhookAckResponse(
            received=True,
            uuid=payload.uuid,
            message="Event processed successfully",
            processed=True,
        )

    async def _handle_valid_visitor_tap(self, payload: NuveqWebhookPayload, tap: TapEvent) -> None:
        """Handles Entry and Exit transitions for a valid visitor tap."""
        stmt = (
            select(Booking)
            .options(selectinload(Booking.room))
            .where(Booking.credential_number == payload.card_no)
        )
        booking = (await self.db.execute(stmt)).scalar_one_or_none()
        if not booking:
            logger.warning(
                f"Valid visitor tap with credential {payload.card_no} has no matching booking in middle service."
            )
            tap.processed = True
            return

        tap.booking_id = booking.id
        event_time = payload.timestamp or datetime.now(timezone.utc)
        direction = (payload.direction or "").strip().lower()

        status_changed = False
        if direction == "entry":
            if booking.status == BookingStatus.BOOKED:
                booking.status = BookingStatus.CHECKED_IN
                booking.checked_in_at = event_time
                status_changed = True
                logger.info(f"Booking {booking.id} ({booking.booker_name}) CHECKED_IN via Entry tap.")
            else:
                logger.info(f"Subsequent Entry tap for booking {booking.id} ignored for state.")

        elif direction == "exit":
            if booking.status == BookingStatus.CHECKED_IN:
                booking.status = BookingStatus.CHECKED_OUT
                booking.checked_out_at = event_time
                status_changed = True
                logger.info(f"Booking {booking.id} ({booking.booker_name}) CHECKED_OUT via Exit tap.")
            else:
                logger.warning(
                    f"Exit tap received for booking {booking.id} in non-checked-in state ({booking.status})."
                )

        tap.processed = True

        if status_changed and booking.room_id:
            # Recalculate room status and notify client webhook
            current_room_status, _ = await self.room_service.get_room_status(booking.room_id)
            await self._dispatch_client_notification(
                ClientWebhookNotification(
                    event_type="booking_status_changed",
                    room_id=booking.room_id,
                    room_status=current_room_status,
                    booking_id=booking.id,
                    booking_status=booking.status,
                    credential_number=booking.credential_number,
                    tap_event_name=payload.name,
                    tap_direction=payload.direction,
                    timestamp=datetime.now(timezone.utc),
                )
            )

    async def _dispatch_client_notification(self, notification: ClientWebhookNotification) -> None:
        """Pushes real-time status updates to the client's registered webhook endpoints."""
        stmt = select(ClientWebhookConfig).where(ClientWebhookConfig.is_active == True)
        configs = (await self.db.execute(stmt)).scalars().all()
        if not configs:
            return

        payload_dict = notification.model_dump(mode="json")
        for conf in configs:
            try:
                headers = {"Content-Type": "application/json"}
                if conf.secret:
                    headers["X-Webhook-Secret"] = conf.secret

                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(conf.url, json=payload_dict, headers=headers)
                    logger.info(f"Client webhook notified at {conf.url}: HTTP {resp.status_code}")
            except Exception as exc:
                logger.error(f"Failed to deliver client webhook to {conf.url}: {exc}")
