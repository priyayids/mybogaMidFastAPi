from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models import RoomStatus


class RoomBase(BaseModel):
    name: str = Field(..., description="Human-readable room name", json_schema_extra={"example": "Ruang Meeting 1"})
    site_id: int = Field(..., description="Nuveq Site ID", json_schema_extra={"example": 167})
    controller_id: int = Field(..., description="Nuveq Controller ID", json_schema_extra={"example": 2228})
    door_number: int = Field(..., description="Nuveq Door Number on the controller", json_schema_extra={"example": 1})
    door_id: int = Field(..., description="Authoritative Nuveq Visitor Door ID", json_schema_extra={"example": 3523})
    lift_group_id: int = Field(default=630, description="Nuveq Lift Group ID (Full Access default)", json_schema_extra={"example": 630})
    grace_minutes: int = Field(default=15, description="Minutes after schedule start before no-show revocation", json_schema_extra={"example": 15})
    is_active: bool = Field(default=True, description="Whether room is available for bookings")


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    site_id: Optional[int] = None
    controller_id: Optional[int] = None
    door_number: Optional[int] = None
    door_id: Optional[int] = None
    lift_group_id: Optional[int] = None
    grace_minutes: Optional[int] = None
    is_active: Optional[bool] = None


class RoomResponse(RoomBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    current_status: RoomStatus = Field(default=RoomStatus.AVAILABLE, description="Computed real-time room status")
    active_booking_id: Optional[str] = Field(default=None, description="Current occupying or reserved booking ID")
    created_at: datetime
    updated_at: datetime
