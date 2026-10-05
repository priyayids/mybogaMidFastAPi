from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus


class BookingCreate(BaseModel):
    room_id: str = Field(..., description="Target Room ID")
    booker_name: str = Field(..., min_length=2, max_length=255, description="Full name of booker")
    booker_email: Optional[EmailStr] = Field(default=None, description="Email for QR pass delivery")
    booker_phone: Optional[str] = Field(default=None, description="Contact phone number")
    visit_start: datetime = Field(..., description="Start of reservation (ISO 8601 with TZ)")
    visit_end: datetime = Field(..., description="End of reservation (ISO 8601 with TZ)")
    notes: Optional[str] = Field(default=None, description="Optional notes or purpose")


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    room_id: str
    credential_number: int = Field(..., description="Generated 8-digit Nuveq credential number")
    visitor_id: Optional[int] = Field(default=None, description="Nuveq Visitor ID")
    visitor_registration_id: Optional[int] = Field(default=None, description="Nuveq Registration ID")

    booker_name: str
    booker_email: Optional[str] = None
    booker_phone: Optional[str] = None

    visit_start: datetime
    visit_end: datetime
    expires_at: datetime = Field(..., description="Time after which no-show auto-revoke triggers")

    status: BookingStatus
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    notes: Optional[str] = None

    qr_data_uri: Optional[str] = Field(default=None, description="Base64 Data URI image of QR code")
    qr_download_url: Optional[str] = Field(default=None, description="Direct download URL for QR image")

    created_at: datetime
    updated_at: datetime


class BookingQrResponse(BaseModel):
    booking_id: str
    credential_number: int
    qr_data_uri: str
