import logging
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.exceptions import NuveqApiError

logger = logging.getLogger(__name__)


class NuveqApiClient:
    """
    High-performance async HTTP client for the Nuveq Cloud Access Control REST API.
    Enforces authentication via X-API-KEY header and standardizes error handling.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or settings.NUVEQ_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.NUVEQ_API_KEY
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                )
            except httpx.RequestError as exc:
                logger.error(f"Network error calling Nuveq API {method} {url}: {exc}")
                raise NuveqApiError(f"Failed to connect to Nuveq API: {str(exc)}")

            if not response.is_success:
                error_msg = f"Nuveq API returned HTTP {response.status_code}: {response.text}"
                logger.error(error_msg)
                raise NuveqApiError(
                    message=f"Nuveq API error: {response.status_code}",
                    status_code=response.status_code,
                    nuveq_response=response.text,
                )

            if response.status_code == 204 or not response.content:
                return None

            try:
                return response.json()
            except Exception:
                return response.text

    # --- Discovery & Configuration Endpoints ---

    async def list_sites(self) -> List[Dict[str, Any]]:
        """Lists all sites (buildings) in the Nuveq account."""
        res = await self._request("GET", "/api/sites")
        return res if isinstance(res, list) else res.get("data", [])

    async def list_controllers(self, site_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lists all controllers in the Nuveq account, optionally filtered by site_id."""
        res = await self._request("GET", "/api/controllers", params={"first": 1000})
        controllers = res if isinstance(res, list) else res.get("data", [])
        if site_id:
            controllers = [
                c for c in controllers
                if isinstance(c.get("site"), dict) and c["site"].get("id") == site_id
            ]
        return controllers

    async def get_controller(self, controller_id: int) -> Dict[str, Any]:
        """Gets detailed information for a single controller including doors."""
        return await self._request("GET", f"/api/controllers/{controller_id}")

    async def list_visitor_doors(self) -> List[Dict[str, Any]]:
        """Authoritative list of visitor-capable doors with controllerId, doorNumber, siteId."""
        res = await self._request("GET", "/api/visitors/doors")
        return res if isinstance(res, list) else res.get("data", [])

    async def list_lift_groups(self, site_id: int) -> List[Dict[str, Any]]:
        """Lists lift groups for a given site."""
        res = await self._request("GET", "/api/visitors/lift-groups", params={"siteId": site_id})
        return res if isinstance(res, list) else res.get("data", [])

    # --- Visitor & Registration Endpoints ---

    async def create_visitor_registration(
        self,
        name: str,
        credential_number: int,
        visit_start: str,
        visit_end: str,
        site_id: int,
        lift_group_id: int,
        allowed_door_ids: List[int],
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates visitor and issues registration window in Nuveq Cloud.
        Returns: { "visitorId": int, "visitorRegistrationId": int }
        """
        payload = {
            "name": name,
            "credentialNumber": credential_number,
            "visitStart": visit_start,
            "visitEnd": visit_end,
            "siteId": site_id,
            "liftGroupId": lift_group_id,
            "allowedDoorIds": allowed_door_ids,
        }
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone

        logger.info(f"Issuing Nuveq visitor registration for '{name}' with credential {credential_number}")
        res = await self._request("POST", "/api/visitors", json_data=payload)
        return res if isinstance(res, dict) else {}

    async def revoke_visitor_registration(self, visitor_registration_id: int) -> bool:
        """
        Revokes a visit window at the reader.
        Endpoint: DELETE /api/visitors/registrations/{visitorRegistrationId}
        """
        logger.info(f"Revoking Nuveq visitor registration ID {visitor_registration_id}")
        await self._request("DELETE", f"/api/visitors/registrations/{visitor_registration_id}")
        return True

    # --- Webhooks & Events ---

    async def configure_webhook(
        self,
        webhook_link: str,
        enable: bool = True,
        webhook_link2: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Configures the account-level webhook URL on Nuveq Cloud."""
        payload: Dict[str, Any] = {
            "enable": enable,
            "webhookLink": webhook_link,
        }
        if webhook_link2:
            payload["webhookLink2"] = webhook_link2

        logger.info(f"Setting Nuveq account webhook to: {webhook_link}")
        return await self._request("POST", "/api/webhooks", json_data=payload)

    async def get_events(
        self,
        date_str: Optional[str] = None,
        after: Optional[int] = None,
        first: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetches events from REST log (reconciliation fallback)."""
        params: Dict[str, Any] = {"first": first}
        if date_str:
            params["date"] = date_str
        if after is not None:
            params["after"] = after

        res = await self._request("GET", "/api/events", params=params)
        return res if isinstance(res, list) else res.get("data", [])
