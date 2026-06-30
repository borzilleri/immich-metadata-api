"""SQL for searching ``asset_metadata``.

The service is agnostic to the metadata key and value shape — it only relies on
the columns Immich enforces: ``asset_metadata(assetId, key, value jsonb)`` and
``asset(id, ownerId)``. The ``asset`` join exists solely to owner-scope results,
since ``ownerId`` lives on ``asset``, not ``asset_metadata``.

No version-specific columns (e.g. ``deviceId``/``deviceAssetId``, removed in
Immich v3) are referenced, so a single build runs unchanged across versions.
"""

from __future__ import annotations

_BASE = """
SELECT am."assetId" AS asset_id, am.value
FROM asset_metadata am
JOIN asset a ON a.id = am."assetId"
WHERE am.key = %(key)s
  AND a."ownerId" = %(owner_id)s
"""

# jsonb containment is index-friendly. jsonb_build_object(text, text) yields a
# JSON object with a string value, matching string-valued fields. The ::text casts
# are required so Postgres can resolve the parameter types (jsonb_build_object is
# variadic "any", so untyped params raise IndeterminateDatatype).
_FIELD_FILTER = '  AND am.value @> jsonb_build_object(%(field)s::text, %(value)s::text)\n'

_ORDER = '  ORDER BY am."assetId"\n'


def search_sql(*, with_field: bool) -> str:
    """Return the search query, adding the value filter only when requested.

    The filter is appended in Python rather than guarded inside SQL so we never
    pass a NULL key to ``jsonb_build_object`` (which would raise).
    """
    return _BASE + (_FIELD_FILTER if with_field else "") + _ORDER
