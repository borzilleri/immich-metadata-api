# immich-metadata-api

A small **read-only** REST service that provides a method to search Immich's 
asset metadata. That is, metadata set on an an asset during creation (with the
`metadata` field), or set/updated with the `/asset/metadata` API endpoint.

Immich does not provide an API to query this, so this provides a service that
lives inside the Immich compose stack and talks directly to the postgres
database.

This service was initially created to work with [photos-immich-sync](https://github.com/borzilleri/photos-immich-sync), to provide the ability to track uploaded assets by the
local & cloud Photos identifiers, since `deviceId` and `deviceAssetId` fields
are being removed in Immich 3.0

## Authentication

This uses Immich API keys, with the same authentication mechanism
(`x-api-key` header). Only assets owned by the API key owner are searched
and returned.

## API

| Route | Description |
|-------|-------------|
| `GET /health` | Liveness + reported version. |
| `GET /info` | Reported version + GitHub update check. No auth. |
| `GET /metadata?key=<key>[&field=<f>&value=<v>]` | Search this owner's `asset_metadata`. |

### `/info`

`/info` reports the running version and checks GitHub releases for a newer one.
The result is cached (see `RELEASE_CACHE_TTL`) and the check is non-fatal — if
GitHub is unreachable, `updateAvailable` is `false`.

```jsonc
{
  "version": "0.1.0",
  "updateAvailable": true,
  "latestVersion": "0.2.0",
  "releaseUrl": "https://github.com/borzilleri/immich-metadata-api/releases/tag/v0.2.0"
}
```

### `/metadata`

- `key` (**required**): the `asset_metadata` key to search.
- `field` + `value` (optional, together): return only assets whose `value` jsonb
  contains `{ field: value }`. Omit both to **enumerate** all of the owner's
  entries for that key.

Response: `[{ "assetId": "<uuid>", "value": { ...the stored jsonb block... } }]`

**Examples:**

```bash
# Resolve an asset by a stored cloud identifier
curl -H "x-api-key: $IMMICH_API_KEY" \
  "https://immich.example.com/metadata?key=io.rampant.photos-immich-sync&field=phAssetCloudIdentifier&value=ABC123"

# Enumerate every asset this owner tagged with the key
curl -H "x-api-key: $IMMICH_API_KEY" \
  "https://immich.example.com/metadata?key=io.rampant.photos-immich-sync"
```

### API key requirement

API Keys used with this service require, at least, the following permissions:

    asset.read
    user.read

## Configuration (environment)

| Variable | Default | Purpose |
|----------|---------|---------|
| `IMMICH_INTERNAL_URL` | `http://immich-server:2283/api` | URL of the Immich API |
| `METADATA_API_DB_URL` | — | Full Postgres conninfo/URL. If set, overrides the `DB_*` vars below. |
| `DB_HOSTNAME` / `DB_PORT` / `DB_USERNAME` / `DB_PASSWORD` / `DB_DATABASE_NAME` | `database` / `5432` / `postgres` / `postgres` / `immich` | Used when `METADATA_API_DB_URL` is unset (mirrors Immich's vars). |
| `AUTH_CACHE_TTL` | `300` | Seconds to cache a key's full validation (validity + `user.read`/`asset.read` + owner id). |
| `APP_VERSION` | `dev` | Reported by `/health` and `/info`; set by the release build. |
| `GITHUB_REPO` | `borzilleri/immich-metadata-api` | `owner/repo` `/info` checks for the latest release. |
| `RELEASE_CACHE_TTL` | `3600` | Seconds to cache the `/info` GitHub release check. |

## Security

- The service issues **only `SELECT`** and additionally sets every DB connection
  to autocommit + read-only, so it cannot mutate data. For defense in depth,
  point it at a **read-only Postgres role** (`GRANT SELECT`), not the superuser.
- Every request must carry a valid Immich API key; all queries are filtered by
  the resolved owner id (no cross-user access).
- Keep Postgres unpublished; expose only this API, ideally behind your existing
  reverse proxy with TLS.

## Deploy

See [`docker-compose.example.yml`](docker-compose.example.yml). Image is published
to `ghcr.io/borzilleri/immich-metadata-api`.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest                 # unit tests (no DB needed)

# Integration tests against a real Postgres:
METADATA_API_TEST_DB=postgresql://postgres:postgres@localhost:5432/immich pytest

# Run locally
uvicorn app.main:app --reload
```

Releases are cut manually via the **Release** GitHub Action (`workflow_dispatch`,
choose a `bump`), which tags `vX.Y.Z`, builds a multi-arch image, and pushes it to
GHCR.
