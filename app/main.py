"""FastAPI application: /health and the owner-scoped /metadata search."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel

from .auth import ImmichAuth
from .config import load_settings
from .db import Database
from .release import ReleaseChecker

settings = load_settings()


class Health(BaseModel):
    status: str
    version: str


class Info(BaseModel):
    version: str
    updateAvailable: bool
    latestVersion: str | None = None
    releaseUrl: str | None = None


class MetadataResult(BaseModel):
    assetId: str
    value: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(settings.db_conninfo)
    await db.open()
    client = httpx.AsyncClient(timeout=10.0)
    app.state.db = db
    app.state.auth = ImmichAuth(settings.immich_internal_url, settings.auth_cache_ttl, client)
    app.state.release = ReleaseChecker(
        settings.github_repo, settings.release_cache_ttl, settings.version, client
    )
    try:
        yield
    finally:
        await client.aclose()
        await db.close()


app = FastAPI(
    title="immich-metadata-api",
    version=settings.version,
    lifespan=lifespan,
    docs_url="/",
    redoc_url=None,
)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_auth(request: Request) -> ImmichAuth:
    return request.app.state.auth


def get_release(request: Request) -> ReleaseChecker:
    return request.app.state.release


async def get_owner(
    auth: Annotated[ImmichAuth, Depends(get_auth)],
    x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
) -> str:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing x-api-key header")
    return await auth.resolve_owner(x_api_key)


@app.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version=settings.version)


@app.get("/info", response_model=Info)
async def info(checker: Annotated[ReleaseChecker, Depends(get_release)]) -> Info:
    release = await checker.check()
    return Info(
        version=settings.version,
        updateAvailable=release.update_available,
        latestVersion=release.latest_version,
        releaseUrl=release.release_url,
    )


@app.get("/metadata", response_model=list[MetadataResult])
async def metadata(
    owner_id: Annotated[str, Depends(get_owner)],
    db: Annotated[Database, Depends(get_db)],
    key: Annotated[str, Query(min_length=1, description="asset_metadata key to search")],
    field: Annotated[
        str | None, Query(description="JSON field within value to match")
    ] = None,
    value: Annotated[str | None, Query(description="value the field must equal")] = None,
) -> list[MetadataResult]:
    if (field is None) != (value is None):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "field and value must be provided together"
        )
    rows = await db.search_metadata(owner_id=owner_id, key=key, field=field, value=value)
    return [MetadataResult(**row) for row in rows]
