from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from app.core.config import settings

api_key_header = APIKeyHeader(
    name="X-Client-API-Key",
    auto_error=False,
    description="Authorized client API key for accessing the middle service",
)


async def verify_client_api_key(
    api_key: str = Security(api_key_header),
) -> str:
    """Verifies that the caller provided a valid registered client API key."""
    if not api_key or api_key not in settings.CLIENT_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Client-API-Key header",
        )
    return api_key


def verify_nuveq_webhook_secret(secret_token: str) -> None:
    """Verifies that the incoming webhook URL path token matches the configured secret."""
    if secret_token != settings.NUVEQ_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid webhook secret token",
        )
