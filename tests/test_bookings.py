from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from tests.conftest import MockNuveqApiClient


@pytest.mark.asyncio
async def test_create_and_cancel_booking(
    async_client: AsyncClient,
    auth_headers: dict,
    mock_nuveq_client: MockNuveqApiClient,
):
    # 1. First create a room
    room_payload = {
        "name": "Ruang Meeting 2",
        "site_id": 167,
        "controller_id": 2228,
        "door_number": 1,
        "door_id": 3524,
        "lift_group_id": 630,
        "grace_minutes": 15,
    }
    room_res = await async_client.post("/api/v1/rooms", json=room_payload, headers=auth_headers)
    room_id = room_res.json()["id"]

    # 2. Create a booking
    now = datetime.now(timezone.utc)
    start_time = now + timedelta(hours=1)
    end_time = now + timedelta(hours=3)

    booking_payload = {
        "room_id": room_id,
        "booker_name": "Rian Kusuma",
        "booker_email": "rian@example.com",
        "booker_phone": "+628123456789",
        "visit_start": start_time.isoformat(),
        "visit_end": end_time.isoformat(),
        "notes": "Product design sync",
    }
    res = await async_client.post("/api/v1/bookings", json=booking_payload, headers=auth_headers)
    assert res.status_code == 201
    booking = res.json()
    assert booking["booker_name"] == "Rian Kusuma"
    assert booking["status"] == "BOOKED"
    assert booking["credential_number"] > 0
    assert booking["visitor_registration_id"] == 199999
    assert booking["qr_data_uri"].startswith("data:image/png;base64,")
    assert booking["qr_download_url"].startswith("/api/v1/bookings/")
    assert len(mock_nuveq_client.created_visitors) == 1

    # 3. Check overlapping booking for same room -> 409 Conflict
    res_overlap = await async_client.post("/api/v1/bookings", json=booking_payload, headers=auth_headers)
    assert res_overlap.status_code == 409

    # 4. Filter bookings
    res_filter = await async_client.get(f"/api/v1/bookings?room_id={room_id}", headers=auth_headers)
    assert res_filter.status_code == 200
    assert len(res_filter.json()) == 1

    # 5. Download QR code directly
    booking_id = booking["id"]
    qr_res = await async_client.get(f"/api/v1/bookings/{booking_id}/qr", headers=auth_headers)
    assert qr_res.status_code == 200
    assert qr_res.headers["content-type"] == "image/png"
    assert len(qr_res.content) > 100

    # 6. Cancel booking -> calls Nuveq revoke_visitor_registration
    cancel_res = await async_client.delete(f"/api/v1/bookings/{booking_id}", headers=auth_headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"
    assert 199999 in mock_nuveq_client.revoked_registrations


@pytest.mark.asyncio
async def test_booking_errors(async_client: AsyncClient, auth_headers: dict):
    # Non-existent booking detail
    res_404 = await async_client.get("/api/v1/bookings/bk_nonexistent", headers=auth_headers)
    assert res_404.status_code == 404

    # Booking with end before start
    now = datetime.now(timezone.utc)
    res_invalid_time = await async_client.post(
        "/api/v1/bookings",
        json={
            "room_id": "rm_nonexistent",
            "booker_name": "Test",
            "visit_start": (now + timedelta(hours=2)).isoformat(),
            "visit_end": (now + timedelta(hours=1)).isoformat(),
        },
        headers=auth_headers,
    )
    assert res_invalid_time.status_code == 404 or res_invalid_time.status_code == 409
