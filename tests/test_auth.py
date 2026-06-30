import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.auth import ImmichAuth


def _auth(handler, ttl=300.0):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ImmichAuth("http://immich:2283/api", ttl, client), client


def _routed_handler(
    *, permissions=("user.read", "asset.read"), me_status=200, key_status=200, counts=None
):
    def handler(request: httpx.Request) -> httpx.Response:
        if counts is not None:
            counts[request.url.path] = counts.get(request.url.path, 0) + 1
        assert request.headers["x-api-key"] == "good-key"
        if request.url.path == "/api/api-keys/me":
            return httpx.Response(key_status, json={"permissions": list(permissions)})
        if request.url.path == "/api/users/me":
            return httpx.Response(me_status, json={"id": "user-123", "email": "a@b.c"})
        raise AssertionError(f"unexpected path {request.url.path}")

    return handler


def test_valid_key_returns_owner_and_caches():
    counts: dict[str, int] = {}
    auth, client = _auth(_routed_handler(counts=counts))
    try:
        assert asyncio.run(auth.resolve_owner("good-key")) == "user-123"
        # second call is served from cache, no extra HTTP requests
        assert asyncio.run(auth.resolve_owner("good-key")) == "user-123"
        assert counts == {"/api/api-keys/me": 1, "/api/users/me": 1}
    finally:
        asyncio.run(client.aclose())


def test_all_scope_is_accepted():
    auth, client = _auth(_routed_handler(permissions=("all",)))
    try:
        assert asyncio.run(auth.resolve_owner("good-key")) == "user-123"
    finally:
        asyncio.run(client.aclose())


@pytest.mark.parametrize("permissions", [("user.read",), ("asset.read",), ()])
def test_missing_required_permission_is_403_without_user_lookup(permissions):
    counts: dict[str, int] = {}
    auth, client = _auth(_routed_handler(permissions=permissions, counts=counts))
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.resolve_owner("good-key"))
        assert exc.value.status_code == 403
        assert "/api/users/me" not in counts
    finally:
        asyncio.run(client.aclose())


def test_invalid_key_on_api_keys_is_401():
    auth, client = _auth(_routed_handler(key_status=401))
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.resolve_owner("good-key"))
        assert exc.value.status_code == 401
    finally:
        asyncio.run(client.aclose())


@pytest.mark.parametrize(
    "key_status,me_status,expected",
    [(500, 200, 502), (200, 401, 401), (200, 500, 502)],
)
def test_error_statuses_map_to_http_exception(key_status, me_status, expected):
    auth, client = _auth(_routed_handler(key_status=key_status, me_status=me_status))
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.resolve_owner("good-key"))
        assert exc.value.status_code == expected
    finally:
        asyncio.run(client.aclose())


def test_network_error_maps_to_502():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    auth, client = _auth(handler)
    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth.resolve_owner("good-key"))
        assert exc.value.status_code == 502
    finally:
        asyncio.run(client.aclose())
