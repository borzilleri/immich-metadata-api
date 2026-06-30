from app.queries import search_sql


def test_with_field_adds_containment_and_order():
    sql = search_sql(with_field=True)
    assert "jsonb_build_object(%(field)s::text, %(value)s::text)" in sql
    assert 'ORDER BY am."assetId"' in sql
    assert 'a."ownerId" = %(owner_id)s' in sql


def test_without_field_omits_containment():
    sql = search_sql(with_field=False)
    assert "jsonb_build_object" not in sql
    # owner scoping is always present, regardless of field filter
    assert 'a."ownerId" = %(owner_id)s' in sql
    assert "am.key = %(key)s" in sql
