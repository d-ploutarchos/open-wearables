from typing import Any

import httpx


class HevyClient:
    """Small API-key client isolated from OAuth-oriented provider helpers."""

    def __init__(self, base_url: str = "https://api.hevyapp.com") -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        api_key: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{self.base_url}{endpoint}",
                headers={"api-key": api_key, "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            return response.json()
