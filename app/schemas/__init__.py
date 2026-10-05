from app.schemas.common import ApiResponse, ErrorResponse
from app.schemas.room import RoomBase, RoomCreate, RoomUpdate, RoomResponse
from app.schemas.booking import (
    BookingCreate,
    BookingResponse,
    BookingQrResponse,
)
from app.schemas.webhook import (
    NuveqWebhookPayload,
    WebhookAckResponse,
    ClientWebhookNotification,
    ClientWebhookConfigCreate,
    ClientWebhookConfigResponse,
)
from app.schemas.nuveq import (
    NuveqSite,
    NuveqController,
    NuveqVisitorDoor,
    NuveqLiftGroup,
    NuveqWebhookSetupRequest,
    NuveqWebhookSetupResponse,
)

__all__ = [
    "ApiResponse",
    "ErrorResponse",
    "RoomBase",
    "RoomCreate",
    "RoomUpdate",
    "RoomResponse",
    "BookingCreate",
    "BookingResponse",
    "BookingQrResponse",
    "NuveqWebhookPayload",
    "WebhookAckResponse",
    "ClientWebhookNotification",
    "ClientWebhookConfigCreate",
    "ClientWebhookConfigResponse",
    "NuveqSite",
    "NuveqController",
    "NuveqVisitorDoor",
    "NuveqLiftGroup",
    "NuveqWebhookSetupRequest",
    "NuveqWebhookSetupResponse",
]
