import pytest
from fastapi.testclient import TestClient

from app.main import app, get_auth, get_db


class FakeAuth:
    def __init__(self, owner_id="owner-1"):
        self.owner_id = owner_id
        self.keys_seen = []

    async def resolve_owner(self, api_key):
        self.keys_seen.append(api_key)
        return self.owner_id


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.last_call = None

    async def search_metadata(self, *, owner_id, key, field=None, value=None):
        self.last_call = {"owner_id": owner_id, "key": key, "field": field, "value": value}
        return self.rows


@pytest.fixture
def client():
    # No `with` block → app lifespan does not run → no real DB/Immich connections.
    return TestClient(app)


def _wire(rows, owner_id="owner-1"):
    fake_auth = FakeAuth(owner_id)
    fake_db = FakeDB(rows)
    app.dependency_overrides[get_auth] = lambda: fake_auth
    app.dependency_overrides[get_db] = lambda: fake_db
    return fake_auth, fake_db


def teardown_function():
    app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_point_lookup_returns_rows_and_scopes_to_owner(client):
    rows = [{"assetId": "a-1", "value": {"cid": "X", "local": "L1"}}]
    fake_auth, fake_db = _wire(rows, owner_id="owner-9")

    resp = client.get(
        "/metadata",
        params={"key": "io.test", "field": "cid", "value": "X"},
        headers={"x-api-key": "abc"},
    )

    assert resp.status_code == 200
    assert resp.json() == rows
    assert fake_auth.keys_seen == ["abc"]
    assert fake_db.last_call == {
        "owner_id": "owner-9",
        "key": "io.test",
        "field": "cid",
        "value": "X",
    }


def test_enumeration_without_field(client):
    _, fake_db = _wire([{"assetId": "a-1", "value": {"cid": "X"}}])

    resp = client.get("/metadata", params={"key": "io.test"}, headers={"x-api-key": "abc"})

    assert resp.status_code == 200
    assert fake_db.last_call["field"] is None
    assert fake_db.last_call["value"] is None


def test_missing_api_key_is_401(client):
    _wire([])
    resp = client.get("/metadata", params={"key": "io.test"})
    assert resp.status_code == 401


def test_field_without_value_is_400(client):
    _wire([])
    resp = client.get(
        "/metadata", params={"key": "io.test", "field": "cid"}, headers={"x-api-key": "abc"}
    )
    assert resp.status_code == 400


def test_key_is_required(client):
    _wire([])
    resp = client.get("/metadata", headers={"x-api-key": "abc"})
    assert resp.status_code == 422
