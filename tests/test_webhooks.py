from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient
from app.core.config import settings


@pytest.mark.asyncio
async def test_webhook_ingestion_and_state_transitions(
    async_client: AsyncClient,
    auth_headers: dict,
):
    secret = settings.NUVEQ_WEBHOOK_SECRET

    # 1. Setup Room and Booking
    room_payload = {
        "name": "Ruang Meeting Webhook Test",
        "site_id": 167,
        "controller_id": 2228,
        "door_number": 1,
        "door_id": 3525,
        "grace_minutes": 15,
    }
    room_res = await async_client.post("/api/v1/rooms", json=room_payload, headers=auth_headers)
    room = room_res.json()
    room_id = room["id"]

    now = datetime.now(timezone.utc)
    booking_payload = {
        "room_id": room_id,
        "booker_name": "Webhook Tester",
        "visit_start": (now - timedelta(minutes=5)).isoformat(),
        "visit_end": (now + timedelta(hours=1)).isoformat(),
    }
    booking_res = await async_client.post("/api/v1/bookings", json=booking_payload, headers=auth_headers)
    booking = booking_res.json()
    booking_id = booking["id"]
    cred_num = booking["credential_number"]

    # 2. Test Invalid Secret Token -> 403 Forbidden
    invalid_url = "/api/v1/webhooks/nuveq/wrong-secret"
    bad_res = await async_client.post(invalid_url, json={"uuid": "test-1", "name": "Status"})
    assert bad_res.status_code == 403

    # 3. Simulate Entry Tap: 'Valid visitor', direction 'Entry'
    webhook_url = f"/api/v1/webhooks/nuveq/{secret}"
    entry_payload = {
        "uuid": "tap-event-entry-001",
        "mac": "E03C1CB330945601",
        "site_id": 167,
        "door_id": 3525,
        "card_no": cred_num,
        "name": "Valid visitor",
        "direction": "Entry",
        "visitor": True,
        "user_name": "Webhook Tester",
        "timestamp": now.isoformat(),
    }
    res_entry = await async_client.post(webhook_url, json=entry_payload)
    assert res_entry.status_code == 200
    ack = res_entry.json()
    assert ack["received"] is True
    assert ack["processed"] is True

    # Verify booking status is now CHECKED_IN
    bk_check = await async_client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers)
    assert bk_check.json()["status"] == "CHECKED_IN"
    assert bk_check.json()["checked_in_at"] is not None

    # Verify room status is now IN_USE
    rm_check = await async_client.get(f"/api/v1/rooms/{room_id}", headers=auth_headers)
    assert rm_check.json()["current_status"] == "IN_USE"

    # 4. Test Idempotency with exact same event uuid -> Duplicate ignored
    res_dup = await async_client.post(webhook_url, json=entry_payload)
    assert res_dup.status_code == 200
    assert res_dup.json()["processed"] is False
    assert "Duplicate" in res_dup.json()["message"]

    # 5. Simulate Exit Tap: 'Valid visitor', direction 'Exit'
    exit_payload = {
        "uuid": "tap-event-exit-002",
        "mac": "E03C1CB330945601",
        "site_id": 167,
        "door_id": 3525,
        "card_no": cred_num,
        "name": "Valid visitor",
        "direction": "Exit",
        "visitor": True,
        "user_name": "Webhook Tester",
        "timestamp": (now + timedelta(minutes=10)).isoformat(),
    }
    res_exit = await async_client.post(webhook_url, json=exit_payload)
    assert res_exit.status_code == 200
    assert res_exit.json()["processed"] is True

    # Verify booking status is now CHECKED_OUT
    bk_check2 = await async_client.get(f"/api/v1/bookings/{booking_id}", headers=auth_headers)
    assert bk_check2.json()["status"] == "CHECKED_OUT"
    assert bk_check2.json()["checked_out_at"] is not None

    # Verify room status is now AVAILABLE again
    rm_check2 = await async_client.get(f"/api/v1/rooms/{room_id}", headers=auth_headers)
    assert rm_check2.json()["current_status"] == "AVAILABLE"
