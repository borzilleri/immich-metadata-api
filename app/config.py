"""Runtime configuration, sourced entirely from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import make_conninfo


def _db_password() -> str:
    """Read the DB password from ``DB_PASSWORD_FILE`` if set (Docker secrets
    pattern), otherwise fall back to the ``DB_PASSWORD`` env var."""
    path = os.getenv("DB_PASSWORD_FILE")
    if path:
        return Path(path).read_text().strip()
    return os.getenv("DB_PASSWORD", "postgres")


def _db_conninfo() -> str:
    """Build a psycopg conninfo string.

    Prefer an explicit ``METADATA_API_DB_URL``; otherwise fall back to Immich's
    standard ``DB_*`` variables so the service drops into a compose stack with no
    extra configuration.
    """
    url = os.getenv("METADATA_API_DB_URL")
    if url:
        return url
    return make_conninfo(
        host=os.getenv("DB_HOSTNAME", "database"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USERNAME", "postgres"),
        password=_db_password(),
        dbname=os.getenv("DB_DATABASE_NAME", "immich"),
    )


@dataclass(frozen=True)
class Settings:
    db_conninfo: str
    immich_internal_url: str
    auth_cache_ttl: float
    version: str
    github_repo: str
    release_cache_ttl: float


def load_settings() -> Settings:
    return Settings(
        db_conninfo=_db_conninfo(),
        immich_internal_url=os.getenv(
            "IMMICH_INTERNAL_URL", "http://immich-server:2283/api"
        ).rstrip("/"),
        auth_cache_ttl=float(os.getenv("AUTH_CACHE_TTL", "300")),
        version=os.getenv("APP_VERSION", "dev"),
        github_repo=os.getenv("GITHUB_REPO", "borzilleri/immich-metadata-api"),
        release_cache_ttl=float(os.getenv("RELEASE_CACHE_TTL", "3600")),
    )
