"""Integration tests against a real Postgres.

Skipped unless ``METADATA_API_TEST_DB`` points at a writable Postgres (CI provides
a service container). Creates a minimal ``asset`` / ``asset_metadata`` schema so it
runs against a bare Postgres, independent of any Immich install.
"""

import asyncio
import os
import uuid

import psycopg
import pytest

from app.db import Database

DSN = os.getenv("METADATA_API_TEST_DB")
pytestmark = pytest.mark.skipif(not DSN, reason="METADATA_API_TEST_DB not set")

OWNER_A = str(uuid.uuid4())
OWNER_B = str(uuid.uuid4())
ASSET_A = str(uuid.uuid4())
ASSET_B = str(uuid.uuid4())
KEY = "io.rampant.photos-immich-sync"


async def _seed():
    async with await psycopg.AsyncConnection.connect(DSN, autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS asset_metadata")
        await conn.execute("DROP TABLE IF EXISTS asset")
        await conn.execute('CREATE TABLE asset (id uuid PRIMARY KEY, "ownerId" uuid NOT NULL)')
        await conn.execute(
            'CREATE TABLE asset_metadata ('
            '"assetId" uuid NOT NULL REFERENCES asset(id), '
            "key varchar NOT NULL, value jsonb NOT NULL, "
            'PRIMARY KEY ("assetId", key))'
        )
        await conn.execute('INSERT INTO asset (id, "ownerId") VALUES (%s, %s)', (ASSET_A, OWNER_A))
        await conn.execute('INSERT INTO asset (id, "ownerId") VALUES (%s, %s)', (ASSET_B, OWNER_B))
        # Both owners share the same cloud-id value, to prove owner isolation.
        await conn.execute(
            'INSERT INTO asset_metadata ("assetId", key, value) VALUES (%s, %s, %s)',
            (ASSET_A, KEY, psycopg.types.json.Jsonb({"phAssetCloudIdentifier": "X", "n": 1})),
        )
        await conn.execute(
            'INSERT INTO asset_metadata ("assetId", key, value) VALUES (%s, %s, %s)',
            (ASSET_B, KEY, psycopg.types.json.Jsonb({"phAssetCloudIdentifier": "X"})),
        )


def test_point_lookup_is_owner_scoped():
    async def run():
        await _seed()
        db = Database(DSN)
        await db.open()
        try:
            rows = await db.search_metadata(
                owner_id=OWNER_A, key=KEY, field="phAssetCloudIdentifier", value="X"
            )
            assert [r["assetId"] for r in rows] == [ASSET_A]
            assert rows[0]["value"]["n"] == 1
        finally:
            await db.close()

    asyncio.run(run())


def test_enumeration_returns_only_owner_entries():
    async def run():
        await _seed()
        db = Database(DSN)
        await db.open()
        try:
            rows = await db.search_metadata(owner_id=OWNER_B, key=KEY)
            assert [r["assetId"] for r in rows] == [ASSET_B]
        finally:
            await db.close()

    asyncio.run(run())


def test_connection_is_read_only():
    async def run():
        await _seed()
        db = Database(DSN)
        await db.open()
        try:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                async with db._pool.connection() as conn:
                    await conn.execute('INSERT INTO asset (id, "ownerId") VALUES (%s, %s)',
                                       (str(uuid.uuid4()), OWNER_A))
        finally:
            await db.close()

    asyncio.run(run())
