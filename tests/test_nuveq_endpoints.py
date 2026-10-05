import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_nuveq_discovery_endpoints(async_client: AsyncClient, auth_headers: dict):
    # 1. Test GET /nuveq/sites
    res_sites = await async_client.get("/api/v1/nuveq/sites", headers=auth_headers)
    assert res_sites.status_code == 200
    sites = res_sites.json()
    assert len(sites) == 1
    assert sites[0]["id"] == 167

    # 2. Test GET /nuveq/doors
    res_doors = await async_client.get("/api/v1/nuveq/doors", headers=auth_headers)
    assert res_doors.status_code == 200
    doors = res_doors.json()
    assert len(doors) == 1
    assert doors[0]["id"] == 3523

    # 3. Test GET /nuveq/controllers
    res_ctrl = await async_client.get("/api/v1/nuveq/controllers", headers=auth_headers)
    assert res_ctrl.status_code == 200
    controllers = res_ctrl.json()
    assert len(controllers) == 1
    assert controllers[0]["id"] == 2228

    # 4. Test GET /nuveq/lift-groups
    res_lg = await async_client.get("/api/v1/nuveq/lift-groups?site_id=167", headers=auth_headers)
    assert res_lg.status_code == 200
    lg = res_lg.json()
    assert len(lg) == 1
    assert lg[0]["id"] == 630

    # 5. Test POST /nuveq/setup-webhook
    wh_payload = {
        "webhook_url": "https://api.our-service.com/api/v1/webhooks/nuveq/secret123",
        "enable": True,
    }
    res_wh = await async_client.post("/api/v1/nuveq/setup-webhook", json=wh_payload, headers=auth_headers)
    assert res_wh.status_code == 200
    data = res_wh.json()
    assert data["data"]["enable"] is True
