from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ResourceConflictException, ResourceNotFoundException
from app.models import Booking, BookingStatus, Room, RoomStatus
from app.schemas.room import RoomCreate, RoomResponse, RoomUpdate

logger = logging.getLogger(__name__)


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_rooms(self) -> List[RoomResponse]:
        """Lists all configured rooms with dynamic real-time status."""
        stmt = (
            select(Room)
            .options(selectinload(Room.bookings))
            .order_by(Room.created_at.asc())
        )
        result = await self.db.execute(stmt)
        rooms = result.scalars().all()

        now = datetime.now(timezone.utc)
        response_list: List[RoomResponse] = []
        for room in rooms:
            status, active_bk_id = self.derive_room_status(room, now)
            resp = RoomResponse.model_validate(room)
            resp.current_status = status
            resp.active_booking_id = active_bk_id
            response_list.append(resp)
        return response_list

    async def get_room(self, room_id: str) -> RoomResponse:
        """Retrieves a single room with real-time status."""
        room = await self._get_room_entity(room_id)
        now = datetime.now(timezone.utc)
        status, active_bk_id = self.derive_room_status(room, now)
        resp = RoomResponse.model_validate(room)
        resp.current_status = status
        resp.active_booking_id = active_bk_id
        return resp

    async def get_room_status(
        self, room_id: str, now: Optional[datetime] = None
    ) -> Tuple[RoomStatus, Optional[str]]:
        """Calculates dynamic room status for a given room ID with loaded bookings."""
        room = await self._get_room_entity(room_id)
        return self.derive_room_status(room, now)

    async def _get_room_entity(self, room_id: str) -> Room:
        stmt = (
            select(Room)
            .where(Room.id == room_id)
            .options(selectinload(Room.bookings))
        )
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()
        if not room:
            raise ResourceNotFoundException(f"Room '{room_id}' not found")
        return room

    async def create_room(self, data: RoomCreate) -> RoomResponse:
        """Registers a room mapped to a Nuveq door."""
        # Ensure door_id is not already mapped to another room
        stmt = select(Room).where(Room.door_id == data.door_id)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise ResourceConflictException(
                f"Door ID {data.door_id} is already mapped to room '{existing.name}' ({existing.id})"
            )

        room = Room(
            name=data.name,
            site_id=data.site_id,
            controller_id=data.controller_id,
            door_number=data.door_number,
            door_id=data.door_id,
            lift_group_id=data.lift_group_id,
            grace_minutes=data.grace_minutes,
            is_active=data.is_active,
        )
        self.db.add(room)
        await self.db.flush()
        await self.db.refresh(room)

        resp = RoomResponse.model_validate(room)
        resp.current_status = RoomStatus.AVAILABLE if room.is_active else RoomStatus.MAINTENANCE
        resp.active_booking_id = None
        return resp

    async def update_room(self, room_id: str, data: RoomUpdate) -> RoomResponse:
        """Updates room details or mapping."""
        room = await self._get_room_entity(room_id)
        update_data = data.model_dump(exclude_unset=True)

        if "door_id" in update_data and update_data["door_id"] != room.door_id:
            stmt = select(Room).where(
                Room.door_id == update_data["door_id"], Room.id != room_id
            )
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            if existing:
                raise ResourceConflictException(
                    f"Door ID {update_data['door_id']} is already mapped to room '{existing.name}'"
                )

        for field, value in update_data.items():
            setattr(room, field, value)

        await self.db.flush()
        await self.db.refresh(room)
        return await self.get_room(room_id)

    async def delete_room(self, room_id: str) -> None:
        """Deletes a room configuration and associated records."""
        room = await self._get_room_entity(room_id)
        await self.db.delete(room)
        await self.db.flush()

    @staticmethod
    def derive_room_status(
        room: Room, now: Optional[datetime] = None
    ) -> Tuple[RoomStatus, Optional[str]]:
        """
        Calculates dynamic room status based on active bookings and check-in state.
        See Section 8 of Agent/nuveq-integration-brief.md.
        """
        if not room.is_active:
            return RoomStatus.MAINTENANCE, None

        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Check if any booking is currently IN_USE (checked-in)
        for bk in room.bookings:
            if bk.status == BookingStatus.CHECKED_IN:
                return RoomStatus.IN_USE, bk.id

        # 2. Check if any booking is currently reserved for the current window
        for bk in room.bookings:
            if bk.status == BookingStatus.BOOKED:
                # Ensure tz-aware comparison
                start = bk.visit_start if bk.visit_start.tzinfo else bk.visit_start.replace(tzinfo=timezone.utc)
                end = bk.visit_end if bk.visit_end.tzinfo else bk.visit_end.replace(tzinfo=timezone.utc)
                if start <= now <= end:
                    return RoomStatus.BOOKED, bk.id

        return RoomStatus.AVAILABLE, None
