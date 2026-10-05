from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Nuveq Access Control Middle Service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./nuveq_middle.db"

    # Nuveq Cloud API
    NUVEQ_BASE_URL: str = "https://api-v2.nuveq.cloud"
    NUVEQ_API_KEY: str = Field(default="demo-nuveq-api-key", description="Master Nuveq API Key")
    NUVEQ_WEBHOOK_SECRET: str = Field(
        default="nuveq_wh_secret_token_123",
        description="Secret token passed in Nuveq webhook URL path",
    )

    # Client API Key Authentication
    CLIENT_API_KEYS: Union[List[str], str] = Field(
        default=["client-dev-key-123"],
        description="Comma-separated or list of authorized client API keys",
    )

    # Business Rules Defaults
    DEFAULT_GRACE_MINUTES: int = 15
    DEFAULT_AUTO_CHECKOUT_BUFFER_MINUTES: int = 15

    # Scheduler Settings
    SCHEDULER_ENABLED: bool = True
    EXPIRY_CHECK_INTERVAL_SECONDS: int = 60
    RECONCILIATION_INTERVAL_SECONDS: int = 300
    RECONCILIATION_ENABLED: bool = False

    # No-show auto-revocation. Disable to keep bookings alive regardless of expires_at.
    # TESTING ONLY: leaves abandoned credentials valid at the reader.
    NO_SHOW_EXPIRY_ENABLED: bool = True

    # Allow bookings whose visit_start is already in the past. TESTING ONLY.
    ALLOW_PAST_VISIT_START: bool = False

    @field_validator("CLIENT_API_KEYS", mode="before")
    @classmethod
    def parse_client_api_keys(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v


settings = Settings()
