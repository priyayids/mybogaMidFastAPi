import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db, get_nuveq_client
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.services.nuveq_client import NuveqApiClient

# In-memory SQLite with StaticPool and shared cache for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:testmemdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class MockNuveqApiClient(NuveqApiClient):
    """Mock Nuveq API client to simulate Nuveq Cloud responses without external network."""

    def __init__(self):
        super().__init__(base_url="https://mock.nuveq.cloud", api_key="mock-key")
        self.revoked_registrations = []
        self.created_visitors = []

    async def create_visitor_registration(self, **kwargs):
        self.created_visitors.append(kwargs)
        return {
            "error": 0,
            "message": "Success",
            "data": {
                "visitorId": 109999,
                "visitorRegistrationId": 199999,
            },
        }

    async def revoke_visitor_registration(self, visitor_registration_id: int):
        self.revoked_registrations.append(visitor_registration_id)
        return True

    async def list_sites(self):
        return [{"id": 167, "name": "GEDUNG A", "city": "Jakarta"}]

    async def list_controllers(self, site_id=None):
        return [{"id": 2228, "name": "Main Controller", "site": {"id": 167}}]

    async def list_visitor_doors(self):
        return [
            {
                "id": 3523,
                "name": "RUANG MEETING 1 GEDUNG A",
                "controllerId": 2228,
                "doorNumber": 1,
                "siteId": 167,
            }
        ]

    async def list_lift_groups(self, site_id: int):
        return [{"id": 630, "description": "Full Access"}]

    async def configure_webhook(self, webhook_link, enable=True, webhook_link2=None):
        return {"error": 0, "message": "Success", "data": {"enable": enable, "webhookLink": webhook_link}}


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mock_nuveq_client() -> MockNuveqApiClient:
    return MockNuveqApiClient()


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession, mock_nuveq_client: MockNuveqApiClient) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    def override_get_nuveq():
        return mock_nuveq_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_nuveq_client] = override_get_nuveq

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict:
    return {"X-Client-API-Key": "client-dev-key-123"}


@pytest.fixture(autouse=True)
def allow_past_visit_start_for_tests():
    """Let tests build bookings with a start time in the past.

    Several tests (expiry, webhook ingestion) need bookings that begin before
    "now". ALLOW_PAST_VISIT_START defaults to False and is read from the
    developer's local .env, so without this the suite silently depends on
    whether testing flags are enabled. Tests must not depend on that.
    """
    original = settings.ALLOW_PAST_VISIT_START
    settings.ALLOW_PAST_VISIT_START = True
    yield
    settings.ALLOW_PAST_VISIT_START = original
