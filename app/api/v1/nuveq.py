from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_nuveq_client
from app.core.security import verify_client_api_key
from app.schemas.nuveq import (
    NuveqController,
    NuveqLiftGroup,
    NuveqSite,
    NuveqVisitorDoor,
    NuveqWebhookSetupRequest,
)
from app.services.nuveq_client import NuveqApiClient

router = APIRouter(
    prefix="/nuveq",
    tags=["Nuveq Admin Discovery"],
    dependencies=[Depends(verify_client_api_key)],
)


@router.get("/sites", response_model=List[NuveqSite])
async def list_nuveq_sites(nuveq_client: NuveqApiClient = Depends(get_nuveq_client)):
    """List available sites from Nuveq Cloud."""
    return await nuveq_client.list_sites()


@router.get("/controllers", response_model=List[NuveqController])
async def list_nuveq_controllers(
    site_id: Optional[int] = Query(default=None, description="Filter by site ID"),
    nuveq_client: NuveqApiClient = Depends(get_nuveq_client),
):
    """List controllers from Nuveq Cloud."""
    return await nuveq_client.list_controllers(site_id=site_id)


@router.get("/doors", response_model=List[NuveqVisitorDoor])
async def list_nuveq_doors(nuveq_client: NuveqApiClient = Depends(get_nuveq_client)):
    """List visitor-capable doors (source of truth for Room mappings)."""
    return await nuveq_client.list_visitor_doors()


@router.get("/lift-groups", response_model=List[NuveqLiftGroup])
async def list_nuveq_lift_groups(
    site_id: int = Query(..., description="Site ID to get lift groups for"),
    nuveq_client: NuveqApiClient = Depends(get_nuveq_client),
):
    """List lift groups for a specific site."""
    return await nuveq_client.list_lift_groups(site_id=site_id)


@router.post("/setup-webhook")
async def setup_account_webhook(
    data: NuveqWebhookSetupRequest,
    nuveq_client: NuveqApiClient = Depends(get_nuveq_client),
):
    """
    Registers the middle service webhook URL with Nuveq Cloud.
    (One-time setup for the Nuveq account).
    """
    return await nuveq_client.configure_webhook(
        webhook_link=data.webhook_url,
        enable=data.enable,
        webhook_link2=data.backup_webhook_url,
    )
