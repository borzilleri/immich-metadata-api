"""Check GitHub releases for a newer version than the one currently running.

The result is cached for a TTL and the check is non-fatal: any GitHub failure
yields a "no update" result rather than an error, so ``/info`` always returns the
current version. Caching also keeps us well under GitHub's unauthenticated
rate limit.

The running version is the un-prefixed ``APP_VERSION`` (e.g. ``0.1.0``) baked in
at build time, while GitHub release tags are ``v``-prefixed (e.g. ``v0.1.0``), so
the leading ``v`` is stripped before comparison.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class ReleaseInfo:
    update_available: bool
    latest_version: str | None = None
    release_url: str | None = None


class ReleaseChecker:
    def __init__(
        self, repo: str, cache_ttl: float, current_version: str, client: httpx.AsyncClient
    ) -> None:
        self._repo = repo
        self._ttl = cache_ttl
        self._current = current_version
        self._client = client
        self._cache: tuple[ReleaseInfo, float] | None = None

    async def check(self) -> ReleaseInfo:
        now = time.monotonic()
        if self._cache and self._cache[1] > now:
            return self._cache[0]

        info = await self._fetch()
        self._cache = (info, now + self._ttl)
        return info

    async def _fetch(self) -> ReleaseInfo:
        try:
            resp = await self._client.get(
                f"https://api.github.com/repos/{self._repo}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
        except httpx.HTTPError:
            return ReleaseInfo(update_available=False)

        if resp.status_code != 200:
            return ReleaseInfo(update_available=False)

        body = resp.json()
        tag = body.get("tag_name")
        url = body.get("html_url")
        if not tag:
            return ReleaseInfo(update_available=False)

        latest = tag[1:] if tag.startswith("v") else tag
        return ReleaseInfo(
            update_available=self._is_newer(latest),
            latest_version=latest,
            release_url=url,
        )

    def _is_newer(self, latest: str) -> bool:
        try:
            return Version(latest) > Version(self._current)
        except InvalidVersion:
            return False
