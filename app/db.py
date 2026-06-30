"""Read-only Postgres access for metadata search."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .queries import search_sql


async def _configure(conn: AsyncConnection) -> None:
    # Defense in depth: even if the role has write privileges, every connection
    # this pool hands out is autocommit + read-only, so a bug cannot mutate data.
    # Note: under autocommit psycopg never opens an explicit transaction block, so
    # `set_read_only()` would never be emitted — set the session GUC directly so it
    # applies to every (implicit-transaction) statement.
    await conn.set_autocommit(True)
    await conn.execute("SET default_transaction_read_only = on")


class Database:
    def __init__(self, conninfo: str) -> None:
        self._pool = AsyncConnectionPool(
            conninfo,
            open=False,
            configure=_configure,
            kwargs={"row_factory": dict_row},
        )

    async def open(self) -> None:
        # Non-blocking: the service starts (and /health responds) even if the DB is
        # briefly unreachable at boot. Connections are established in the background
        # and lazily on first use.
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    async def search_metadata(
        self,
        *,
        owner_id: str,
        key: str,
        field: str | None = None,
        value: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = search_sql(with_field=field is not None)
        params = {"owner_id": owner_id, "key": key, "field": field, "value": value}
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()
        return [{"assetId": str(row["asset_id"]), "value": row["value"]} for row in rows]
