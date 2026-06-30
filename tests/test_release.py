import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_release
from app.release import ReleaseChecker, ReleaseInfo

LATEST_PATH = "/repos/borzilleri/immich-metadata-api/releases/latest"
RELEASE_URL = "https://github.com/borzilleri/immich-metadata-api/releases/tag/v0.2.0"


def _checker(handler, current="0.1.0", ttl=3600.0):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ReleaseChecker("borzilleri/immich-metadata-api", ttl, current, client), client


def _release_handler(tag="v0.2.0", url=RELEASE_URL, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == LATEST_PATH
        return httpx.Response(status, json={"tag_name": tag, "html_url": url})

    return handler


def test_newer_release_flags_update():
    checker, client = _checker(_release_handler())
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info == ReleaseInfo(
        update_available=True, latest_version="0.2.0", release_url=RELEASE_URL
    )


def test_same_version_no_update_but_surfaces_latest():
    checker, client = _checker(_release_handler(tag="v0.1.0"), current="0.1.0")
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info.update_available is False
    assert info.latest_version == "0.1.0"


def test_older_release_no_update():
    checker, client = _checker(_release_handler(tag="v0.0.1"), current="0.1.0")
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info.update_available is False
    assert info.latest_version == "0.0.1"


def test_unparseable_current_version_surfaces_latest_without_update():
    checker, client = _checker(_release_handler(), current="dev")
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info.update_available is False
    assert info.latest_version == "0.2.0"
    assert info.release_url == RELEASE_URL


def test_tag_without_v_prefix_is_compared():
    checker, client = _checker(_release_handler(tag="0.2.0"), current="0.1.0")
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info.update_available is True
    assert info.latest_version == "0.2.0"


@pytest.mark.parametrize("status", [404, 500])
def test_non_200_is_non_fatal(status):
    checker, client = _checker(_release_handler(status=status))
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info == ReleaseInfo(update_available=False)


def test_network_error_is_non_fatal():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    checker, client = _checker(handler)
    try:
        info = asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert info == ReleaseInfo(update_available=False)


def test_result_is_cached_within_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"tag_name": "v0.2.0", "html_url": RELEASE_URL})

    checker, client = _checker(handler)
    try:
        asyncio.run(checker.check())
        asyncio.run(checker.check())
    finally:
        asyncio.run(client.aclose())
    assert calls["n"] == 1


class FakeChecker:
    def __init__(self, info):
        self.info = info

    async def check(self):
        return self.info


@pytest.fixture
def client():
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_info_endpoint_reports_update(client):
    app.dependency_overrides[get_release] = lambda: FakeChecker(
        ReleaseInfo(update_available=True, latest_version="0.2.0", release_url=RELEASE_URL)
    )
    resp = client.get("/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["updateAvailable"] is True
    assert body["latestVersion"] == "0.2.0"
    assert body["releaseUrl"] == RELEASE_URL
    assert "version" in body


def test_info_endpoint_needs_no_api_key(client):
    app.dependency_overrides[get_release] = lambda: FakeChecker(
        ReleaseInfo(update_available=False)
    )
    resp = client.get("/info")
    assert resp.status_code == 200
    assert resp.json()["updateAvailable"] is False
    assert resp.json()["latestVersion"] is None
