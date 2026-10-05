from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_client_api_key
from app.services.booking_service import BookingService
from app.services.nuveq_client import NuveqApiClient
from app.services.room_service import RoomService
from app.services.webhook_service import WebhookService


def get_nuveq_client() -> NuveqApiClient:
    return NuveqApiClient()


def get_room_service(db: AsyncSession = Depends(get_db)) -> RoomService:
    return RoomService(db)


def get_booking_service(
    db: AsyncSession = Depends(get_db),
    nuveq_client: NuveqApiClient = Depends(get_nuveq_client),
) -> BookingService:
    return BookingService(db, nuveq_client)


def get_webhook_service(db: AsyncSession = Depends(get_db)) -> WebhookService:
    return WebhookService(db)
