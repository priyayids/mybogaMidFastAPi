from typing import Any, List, Optional
from pydantic import BaseModel, Field


class NuveqSite(BaseModel):
    id: int
    name: str
    contactName: Optional[str] = None
    contactEmail: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    model_config = {"extra": "allow"}


class NuveqController(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    mac: Optional[str] = None
    mode: Optional[str] = None
    site: Optional[dict] = None
    model_config = {"extra": "allow"}


class NuveqVisitorDoor(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    controllerId: int
    doorNumber: int
    siteId: int
    model_config = {"extra": "allow"}


class NuveqLiftGroup(BaseModel):
    id: int
    description: str
    model_config = {"extra": "allow"}


class NuveqWebhookSetupRequest(BaseModel):
    webhook_url: str = Field(..., description="Public HTTPS URL of this middle service webhook endpoint")
    enable: bool = Field(default=True)
    backup_webhook_url: Optional[str] = None


class NuveqWebhookSetupResponse(BaseModel):
    owner_id: Optional[int] = None
    enable: bool
    webhook_link: str
