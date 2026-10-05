from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.models import BookingStatus, RoomStatus


class NuveqWebhookPayload(BaseModel):
    """
    Direct schema mapping the live captured Nuveq Webhook payload (snake_case).
    See section 2.4 in Agent/nuveq-integration-brief.md.
    """
    uuid: str = Field(..., description="Unique event UUID, serves as idempotency key")
    mac: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    site_id: Optional[int] = None
    site_name: Optional[str] = None
    card_id: Optional[int] = 0
    card_no: Optional[int] = Field(default=0, description="Nuveq credential number, joins to booking")
    door_id: Optional[int] = Field(default=0, description="Door ID where tap occurred")
    name: str = Field(..., description="Event name: 'Valid visitor', 'Valid access', 'Invalid access', etc.")
    direction: Optional[str] = Field(default=None, description="'Entry' | 'Exit' | 'Status'")
    timestamp: Optional[datetime] = None
    timezone: Optional[str] = None
    visitor: Optional[bool] = None
    visitcheckin: Optional[bool] = None
    user_name: Optional[str] = None
    email: Optional[str] = None
    type: Optional[str] = None
    alarmevent: Optional[bool] = None
    level: Optional[int] = None

    # Allow extra fields without breaking
    model_config = {"extra": "allow"}


class WebhookAckResponse(BaseModel):
    received: bool = True
    uuid: str
    message: str = "Event accepted"
    processed: bool = True


class ClientWebhookNotification(BaseModel):
    event_type: str = Field(..., description="'room_status_changed' | 'booking_status_changed'")
    room_id: str
    room_status: RoomStatus
    booking_id: Optional[str] = None
    booking_status: Optional[BookingStatus] = None
    credential_number: Optional[int] = None
    tap_event_name: Optional[str] = None
    tap_direction: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ClientWebhookConfigCreate(BaseModel):
    url: str = Field(..., description="Target HTTPS webhook URL on client server")
    secret: Optional[str] = Field(default=None, description="Optional shared secret for HMAC signature")
    is_active: bool = Field(default=True)


class ClientWebhookConfigResponse(BaseModel):
    id: str
    url: str
    secret: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
