"""Authenticate callers by validating their Immich API key against Immich.

A valid key resolves to its owning user's id, which is used to owner-scope every
DB query. The service holds no secrets of its own — it forwards the caller's
``x-api-key`` to Immich and trusts Immich's verdict.

The key must additionally carry both the ``user.read`` and ``asset.read``
permissions (the ``all`` scope satisfies both). Both are checked up front from a
single ``/api-keys/me`` response, so ``/users/me`` is only used to resolve the
owner id. A successful validation (validity + permissions + owner) is cached.
"""

from __future__ import annotations

import time

import httpx
from fastapi import HTTPException, status

REQUIRED_PERMISSIONS = ("user.read", "asset.read")
WILDCARD_PERMISSION = "all"


class ImmichAuth:
    def __init__(self, base_url: str, cache_ttl: float, client: httpx.AsyncClient) -> None:
        self._base = base_url
        self._ttl = cache_ttl
        self._client = client
        # api_key -> (owner_id, expires_at). In-memory only.
        self._cache: dict[str, tuple[str, float]] = {}

    async def resolve_owner(self, api_key: str) -> str:
        now = time.monotonic()
        cached = self._cache.get(api_key)
        if cached and cached[1] > now:
            return cached[0]

        self._verify_permissions(await self._get("/api-keys/me", api_key))
        owner_id = self._resolve_owner_id(await self._get("/users/me", api_key))

        self._cache[api_key] = (owner_id, now + self._ttl)
        return owner_id

    async def _get(self, path: str, api_key: str) -> httpx.Response:
        try:
            return await self._client.get(
                f"{self._base}{path}", headers={"x-api-key": api_key}
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Unable to reach Immich to validate the API key",
            ) from exc

    def _verify_permissions(self, resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Immich API key")
        if resp.status_code != 200:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"Unexpected response from Immich while validating API key: {resp.status_code}",
            )

        permissions = set(resp.json().get("permissions", []))
        if WILDCARD_PERMISSION in permissions:
            return
        missing = [p for p in REQUIRED_PERMISSIONS if p not in permissions]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"API key lacks required permission(s): {', '.join(missing)} "
                f"(use a key with these permissions or the '{WILDCARD_PERMISSION}' scope)",
            )

    def _resolve_owner_id(self, resp: httpx.Response) -> str:
        if resp.status_code == 200:
            return resp.json()["id"]
        if resp.status_code == 401:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Immich API key")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Unexpected response from Immich while resolving the owner: {resp.status_code}",
        )
