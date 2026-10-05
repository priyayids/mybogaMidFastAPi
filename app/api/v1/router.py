from fastapi import APIRouter

from app.api.v1.bookings import router as bookings_router
from app.api.v1.health import router as health_router
from app.api.v1.nuveq import router as nuveq_router
from app.api.v1.rooms import router as rooms_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(rooms_router)
api_v1_router.include_router(bookings_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(nuveq_router)
