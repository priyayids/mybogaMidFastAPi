import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_room(async_client: AsyncClient, auth_headers: dict):
    # 1. Create a room mapped to Nuveq door 3523
    room_payload = {
        "name": "Ruang Meeting 1",
        "site_id": 167,
        "controller_id": 2228,
        "door_number": 1,
        "door_id": 3523,
        "lift_group_id": 630,
        "grace_minutes": 15,
        "is_active": True,
    }
    res = await async_client.post("/api/v1/rooms", json=room_payload, headers=auth_headers)
    assert res.status_code == 201
    room = res.json()
    assert room["name"] == "Ruang Meeting 1"
    assert room["door_id"] == 3523
    assert room["current_status"] == "AVAILABLE"
    assert room["id"].startswith("rm_")

    # 2. Try creating duplicate door mapping -> 409 Conflict
    res_dup = await async_client.post("/api/v1/rooms", json=room_payload, headers=auth_headers)
    assert res_dup.status_code == 409

    # 3. List rooms
    res_list = await async_client.get("/api/v1/rooms", headers=auth_headers)
    assert res_list.status_code == 200
    rooms = res_list.json()
    assert len(rooms) == 1
    assert rooms[0]["id"] == room["id"]

    # 4. Patch room to inactive (maintenance)
    room_id = room["id"]
    res_patch = await async_client.patch(
        f"/api/v1/rooms/{room_id}",
        json={"is_active": False, "name": "Ruang Meeting 1 (Renovating)"},
        headers=auth_headers,
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["current_status"] == "MAINTENANCE"
    assert res_patch.json()["name"] == "Ruang Meeting 1 (Renovating)"

    # 5. Delete room
    res_del = await async_client.delete(f"/api/v1/rooms/{room_id}", headers=auth_headers)
    assert res_del.status_code == 204

    # 6. Verify 404 after delete
    res_404 = await async_client.get(f"/api/v1/rooms/{room_id}", headers=auth_headers)
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_room_unauthorized(async_client: AsyncClient):
    # Without X-Client-API-Key header
    res = await async_client.get("/api/v1/rooms")
    assert res.status_code == 422 or res.status_code == 401
