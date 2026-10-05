from typing import List
from fastapi import APIRouter, Depends, status

from app.api.deps import get_room_service
from app.core.security import verify_client_api_key
from app.schemas.room import RoomCreate, RoomResponse, RoomUpdate
from app.services.room_service import RoomService

router = APIRouter(
    prefix="/rooms",
    tags=["Rooms"],
    dependencies=[Depends(verify_client_api_key)],
)


@router.get("", response_model=List[RoomResponse])
async def list_rooms(room_service: RoomService = Depends(get_room_service)):
    """
    List all registered rooms along with their dynamic real-time status
    (AVAILABLE, BOOKED, IN_USE, EXPIRED, MAINTENANCE).
    """
    return await room_service.list_rooms()


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: str, room_service: RoomService = Depends(get_room_service)):
    """Retrieve a single room with its live status."""
    return await room_service.get_room(room_id)


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    data: RoomCreate, room_service: RoomService = Depends(get_room_service)
):
    """
    Register a meeting room mapped to a Nuveq door and site.
    Enforces that door_id cannot be mapped to multiple rooms.
    """
    return await room_service.create_room(data)


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: str,
    data: RoomUpdate,
    room_service: RoomService = Depends(get_room_service),
):
    """Update room configuration or door mapping."""
    return await room_service.update_room(room_id, data)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str, room_service: RoomService = Depends(get_room_service)
):
    """Delete a room configuration and associated mappings."""
    await room_service.delete_room(room_id)
    return None
