from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Room
from app.services.scheduler_service import SchedulerService
from tests.conftest import MockNuveqApiClient, TestingSessionLocal


@pytest.mark.asyncio
async def test_no_show_auto_expiry(db_session: AsyncSession, mock_nuveq_client: MockNuveqApiClient):
    # 1. Create a room with 15 minutes grace
    room = Room(
        name="Ruang Expiry Test",
        site_id=167,
        controller_id=2228,
        door_number=1,
        door_id=3526,
        grace_minutes=15,
    )
    db_session.add(room)
    await db_session.flush()

    # 2. Create a booking where visit_start was 20 minutes ago (past grace period)
    now = datetime.now(timezone.utc)
    visit_start = now - timedelta(minutes=20)
    visit_end = now + timedelta(hours=1)
    expires_at = visit_start + timedelta(minutes=15)  # 5 minutes ago

    booking = Booking(
        room_id=room.id,
        credential_number=77889900,
        visitor_id=106443,
        visitor_registration_id=191975,
        booker_name="No-Show User",
        visit_start=visit_start,
        visit_end=visit_end,
        expires_at=expires_at,
        status=BookingStatus.BOOKED,
    )
    db_session.add(booking)
    await db_session.commit()

    # 3. Instantiate SchedulerService with our test session factory and mock nuveq client
    scheduler = SchedulerService(
        session_factory=TestingSessionLocal,
        nuveq_client=mock_nuveq_client,
    )

    await scheduler.check_and_expire_no_shows()

    # 4. Verify booking is now EXPIRED
    await db_session.refresh(booking)
    assert booking.status == BookingStatus.EXPIRED

    # 5. Verify Nuveq Cloud revocation endpoint was invoked with registration 191975
    assert 191975 in mock_nuveq_client.revoked_registrations


@pytest.mark.asyncio
async def test_auto_checkout_job(db_session: AsyncSession, mock_nuveq_client: MockNuveqApiClient):
    # 1. Create room
    room = Room(
        name="Ruang Auto Checkout Test",
        site_id=167,
        controller_id=2228,
        door_number=1,
        door_id=3527,
        grace_minutes=15,
    )
    db_session.add(room)
    await db_session.flush()

    # 2. Create checked-in booking past visit_end + 15 min buffer
    now = datetime.now(timezone.utc)
    visit_start = now - timedelta(hours=2)
    visit_end = now - timedelta(minutes=30)  # Ended 30 mins ago
    expires_at = visit_start + timedelta(minutes=15)

    booking = Booking(
        room_id=room.id,
        credential_number=77889901,
        visitor_id=106444,
        visitor_registration_id=191976,
        booker_name="Auto Checkout Booker",
        visit_start=visit_start,
        visit_end=visit_end,
        expires_at=expires_at,
        status=BookingStatus.CHECKED_IN,
        checked_in_at=visit_start,
    )
    db_session.add(booking)
    await db_session.commit()

    # 3. Execute auto check-out job
    scheduler = SchedulerService(
        session_factory=TestingSessionLocal,
        nuveq_client=mock_nuveq_client,
    )
    await scheduler.check_auto_checkout()

    # 4. Verify status is AUTO_CHECKED_OUT
    await db_session.refresh(booking)
    assert booking.status == BookingStatus.AUTO_CHECKED_OUT
    assert booking.checked_out_at is not None
