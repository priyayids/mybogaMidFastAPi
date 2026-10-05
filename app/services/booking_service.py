from datetime import datetime, timedelta, timezone
import logging
import random
from typing import List, Optional
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    NuveqApiError,
    ResourceConflictException,
    ResourceNotFoundException,
)
from app.models import Booking, BookingStatus, Room
from app.schemas.booking import BookingCreate, BookingResponse
from app.core.config import settings
from app.services.nuveq_client import NuveqApiClient
from app.services.qr_service import QrService

logger = logging.getLogger(__name__)


class BookingService:
    def __init__(self, db: AsyncSession, nuveq_client: Optional[NuveqApiClient] = None) -> None:
        self.db = db
        self.nuveq_client = nuveq_client or NuveqApiClient()

    async def _generate_unique_credential_number(self) -> int:
        """Generates a random unique 8-digit numeric credential number."""
        for _ in range(20):
            candidate = random.randint(10000000, 99999999)
            stmt = select(Booking.id).where(Booking.credential_number == candidate)
            exists = (await self.db.execute(stmt)).scalar_one_or_none()
            if not exists:
                return candidate
        raise ResourceConflictException("Failed to generate unique credential number")

    async def create_booking(self, data: BookingCreate) -> BookingResponse:
        """
        Creates a room booking, syncs visitor registration with Nuveq Cloud,
        generates reader QR credential, and stores the booking record.
        """
        # 1. Fetch room
        stmt = select(Room).where(Room.id == data.room_id)
        room = (await self.db.execute(stmt)).scalar_one_or_none()
        if not room:
            raise ResourceNotFoundException(f"Room '{data.room_id}' not found")
        if not room.is_active:
            raise ResourceConflictException(f"Room '{room.name}' is currently unavailable (maintenance)")

        # 2. Validate booking time window
        start_tz = data.visit_start if data.visit_start.tzinfo else data.visit_start.replace(tzinfo=timezone.utc)
        end_tz = data.visit_end if data.visit_end.tzinfo else data.visit_end.replace(tzinfo=timezone.utc)
        if end_tz <= start_tz:
            raise ResourceConflictException("visit_end must be later than visit_start")
        if not settings.ALLOW_PAST_VISIT_START and start_tz < datetime.now(timezone.utc):
            raise ResourceConflictException(
                f"visit_start ({start_tz.isoformat()}) is in the past; "
                "a booking would be immediately eligible for no-show expiry"
            )

        # 3. Check for overlapping active bookings for this room
        overlap_stmt = select(Booking).where(
            and_(
                Booking.room_id == room.id,
                Booking.status.in_([BookingStatus.BOOKED, BookingStatus.CHECKED_IN]),
                Booking.visit_start < end_tz,
                Booking.visit_end > start_tz,
            )
        )
        overlap = (await self.db.execute(overlap_stmt)).scalars().first()
        if overlap:
            raise ResourceConflictException(
                f"Room '{room.name}' is already reserved between {overlap.visit_start.isoformat()} and {overlap.visit_end.isoformat()}"
            )

        # 4. Generate credential number
        credential_number = await self._generate_unique_credential_number()

        # 5. Call Nuveq API to create Visitor and Registration
        try:
            nuveq_res = await self.nuveq_client.create_visitor_registration(
                name=data.booker_name,
                credential_number=credential_number,
                visit_start=start_tz.isoformat(),
                visit_end=end_tz.isoformat(),
                site_id=room.site_id,
                lift_group_id=room.lift_group_id,
                allowed_door_ids=[room.door_id],
                email=data.booker_email,
                phone=data.booker_phone,
            )
            # Response may contain visitorId and visitorRegistrationId directly or under "data"
            data_dict = nuveq_res.get("data", nuveq_res) if isinstance(nuveq_res, dict) else {}
            visitor_id = data_dict.get("visitorId") or data_dict.get("id")
            visitor_reg_id = data_dict.get("visitorRegistrationId") or data_dict.get("registrationId")
        except NuveqApiError as exc:
            logger.error(f"Nuveq visitor creation failed: {exc}")
            raise

        # 6. Compute expiry timestamp (visit_start + grace_minutes)
        expires_at = start_tz + timedelta(minutes=room.grace_minutes)

        # 7. Persist booking
        booking = Booking(
            room_id=room.id,
            credential_number=credential_number,
            visitor_id=visitor_id,
            visitor_registration_id=visitor_reg_id,
            booker_name=data.booker_name,
            booker_email=data.booker_email,
            booker_phone=data.booker_phone,
            visit_start=start_tz,
            visit_end=end_tz,
            expires_at=expires_at,
            status=BookingStatus.BOOKED,
            notes=data.notes,
        )
        self.db.add(booking)
        await self.db.flush()
        await self.db.refresh(booking)

        return self._format_booking_response(booking)

    async def get_booking(self, booking_id: str) -> BookingResponse:
        """Retrieves booking detail by ID."""
        booking = await self._get_booking_entity(booking_id)
        return self._format_booking_response(booking)

    async def list_bookings(
        self,
        room_id: Optional[str] = None,
        status: Optional[BookingStatus] = None,
    ) -> List[BookingResponse]:
        """Lists bookings optionally filtered by room or status."""
        stmt = select(Booking).order_by(Booking.visit_start.desc())
        if room_id:
            stmt = stmt.where(Booking.room_id == room_id)
        if status:
            stmt = stmt.where(Booking.status == status)

        result = await self.db.execute(stmt)
        bookings = result.scalars().all()
        return [self._format_booking_response(b) for b in bookings]

    async def cancel_booking(self, booking_id: str) -> BookingResponse:
        """
        Cancels booking and immediately revokes reader access in Nuveq Cloud.
        """
        booking = await self._get_booking_entity(booking_id)
        if booking.status in [BookingStatus.CANCELLED, BookingStatus.EXPIRED]:
            return self._format_booking_response(booking)

        # Revoke at Nuveq reader if registration was created
        if booking.visitor_registration_id:
            try:
                await self.nuveq_client.revoke_visitor_registration(booking.visitor_registration_id)
            except NuveqApiError as exc:
                logger.warning(f"Could not revoke Nuveq registration {booking.visitor_registration_id}: {exc}")

        booking.status = BookingStatus.CANCELLED
        await self.db.flush()
        await self.db.refresh(booking)
        return self._format_booking_response(booking)

    async def get_booking_qr_bytes(self, booking_id: str) -> bytes:
        """Generates raw PNG image bytes of the booking QR code."""
        booking = await self._get_booking_entity(booking_id)
        return QrService.generate_qr_bytes(booking.credential_number)

    async def _get_booking_entity(self, booking_id: str) -> Booking:
        stmt = select(Booking).where(Booking.id == booking_id)
        result = await self.db.execute(stmt)
        booking = result.scalar_one_or_none()
        if not booking:
            raise ResourceNotFoundException(f"Booking '{booking_id}' not found")
        return booking

    def _format_booking_response(self, booking: Booking) -> BookingResponse:
        qr_uri = QrService.generate_qr_data_uri(booking.credential_number)
        resp = BookingResponse.model_validate(booking)
        resp.qr_data_uri = qr_uri
        resp.qr_download_url = f"/api/v1/bookings/{booking.id}/qr"
        return resp
