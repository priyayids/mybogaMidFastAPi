from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import get_booking_service
from app.core.security import verify_client_api_key
from app.models import BookingStatus
from app.schemas.booking import BookingCreate, BookingResponse
from app.services.booking_service import BookingService

router = APIRouter(
    prefix="/bookings",
    tags=["Bookings"],
    dependencies=[Depends(verify_client_api_key)],
)


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    data: BookingCreate,
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Create a new meeting room booking.
    - Generates unique numeric credential number.
    - Registers visitor with Nuveq Cloud.
    - Issues QR credential pass.
    - Calculates no-show expiry timestamp based on room grace minutes.
    """
    return await booking_service.create_booking(data)


@router.get("", response_model=List[BookingResponse])
async def list_bookings(
    room_id: Optional[str] = Query(default=None, description="Filter by room ID"),
    status: Optional[BookingStatus] = Query(default=None, description="Filter by booking status"),
    booking_service: BookingService = Depends(get_booking_service),
):
    """List bookings with optional filtering."""
    return await booking_service.list_bookings(room_id=room_id, status=status)


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: str,
    booking_service: BookingService = Depends(get_booking_service),
):
    """Retrieve detailed booking record including check-in/out status and QR code."""
    return await booking_service.get_booking(booking_id)


@router.delete("/{booking_id}", response_model=BookingResponse)
async def cancel_booking(
    booking_id: str,
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Cancel booking and immediately revoke credential access at Nuveq door readers.
    """
    return await booking_service.cancel_booking(booking_id)


@router.get("/{booking_id}/qr")
async def download_booking_qr(
    booking_id: str,
    booking_service: BookingService = Depends(get_booking_service),
):
    """
    Directly returns the PNG image binary for the credential QR code.
    Can be used in <img> tags or emailed directly.
    """
    image_bytes = await booking_service.get_booking_qr_bytes(booking_id)
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="qr-{booking_id}.png"'},
    )
