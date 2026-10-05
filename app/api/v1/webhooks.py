from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_webhook_service
from app.core.security import verify_client_api_key, verify_nuveq_webhook_secret
from app.models import ClientWebhookConfig
from app.schemas.webhook import (
    ClientWebhookConfigCreate,
    ClientWebhookConfigResponse,
    NuveqWebhookPayload,
    WebhookAckResponse,
)
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/nuveq/{secret_token}", response_model=WebhookAckResponse)
async def receive_nuveq_webhook(
    secret_token: str,
    payload: NuveqWebhookPayload,
    webhook_service: WebhookService = Depends(get_webhook_service),
):
    """
    Inbound webhook receiver for Nuveq Cloud access events.
    Secured by URL path secret token.
    Processes:
    - Deduplication by event UUID.
    - Check-in on 'Valid visitor' Entry.
    - Check-out on 'Valid visitor' Exit.
    - Outbound push to client webhooks.
    """
    verify_nuveq_webhook_secret(secret_token)
    return await webhook_service.process_nuveq_webhook(payload)


@router.post(
    "/client-config",
    response_model=ClientWebhookConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_client_api_key)],
)
async def register_client_webhook(
    data: ClientWebhookConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Configure a webhook endpoint on the client system to receive real-time room status updates.
    """
    config = ClientWebhookConfig(
        url=data.url,
        secret=data.secret,
        is_active=data.is_active,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


@router.get(
    "/client-config",
    response_model=List[ClientWebhookConfigResponse],
    dependencies=[Depends(verify_client_api_key)],
)
async def list_client_webhooks(db: AsyncSession = Depends(get_db)):
    """List configured client outbound webhooks."""
    stmt = select(ClientWebhookConfig).order_by(ClientWebhookConfig.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()
