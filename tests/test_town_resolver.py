from sqlalchemy import create_engine, select
from sqlalchemy.engine import Connection

from scraper.db import metadata, towns_table
from scraper.gazetteer import load_towns
from scraper.location_resolver import parse_location
from scraper.town_resolver import resolve_town


def _conn_with_gazetteer() -> Connection:
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    conn = engine.connect()
    load_towns(conn)
    conn.commit()
    return conn


def _town_id(conn: Connection, ascii_name: str, country_code: str, admin1_code: str | None = None) -> int:
    query = select(towns_table.c.id).where(
        towns_table.c.ascii_name == ascii_name, towns_table.c.country_code == country_code
    )
    if admin1_code is not None:
        query = query.where(towns_table.c.admin1_code == admin1_code)
    return conn.execute(query).scalar_one()


def test_resolve_town_exact_city_region_country():
    conn = _conn_with_gazetteer()
    p = parse_location("San Francisco, California, United States")
    town_id = resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code)
    assert town_id == _town_id(conn, "San Francisco", "US", "CA")


def test_resolve_town_two_token_city_state_shape():
    conn = _conn_with_gazetteer()
    p = parse_location("New York, NY")
    assert p.city == "New York"
    assert p.region == "NY"
    town_id = resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code)
    # GeoNames' own ascii_name for this town is "New York City" — "New
    # York" only appears in its alternate_names, so this specifically
    # exercises the Tier 3 alias-match path, not an exact ascii_name match.
    assert town_id == _town_id(conn, "New York City", "US", "NY")


def test_resolve_town_disambiguates_same_name_different_state_via_region():
    conn = _conn_with_gazetteer()
    # Three real US towns are named "Washington" (DC, IL, UT) — only the
    # region-scoped tier can tell them apart; without "DC" this must refuse
    # to guess (see test_resolve_town_ambiguous_same_name_no_region below).
    p = parse_location("Washington, DC")
    town_id = resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code)
    assert town_id == _town_id(conn, "Washington", "US", "DC")


def test_resolve_town_ambiguous_same_name_no_region_returns_none():
    conn = _conn_with_gazetteer()
    # No region signal at all here to disambiguate the 3 US "Washington"s.
    town_id = resolve_town(conn, city="Washington", region=None, country_code="US")
    assert town_id is None


def test_resolve_town_disambiguates_via_full_state_name():
    conn = _conn_with_gazetteer()
    # Two real US towns are named "Quincy" (IL and MA) — only a region
    # signal (full name, no 2-letter code available) can disambiguate.
    p = parse_location("Quincy, Massachusetts")
    assert p.region == "Massachusetts"
    town_id = resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code)
    assert town_id == _town_id(conn, "Quincy", "US", "MA")

    other_p = parse_location("Quincy, Illinois")
    other_town_id = resolve_town(
        conn, city=other_p.city, region=other_p.region, country_code=other_p.country_code
    )
    assert other_town_id == _town_id(conn, "Quincy", "US", "IL")
    assert other_town_id != town_id


def test_resolve_town_canada_admin1_numeric_code_mapping():
    conn = _conn_with_gazetteer()
    p = parse_location("Toronto, Ontario, Canada")
    assert p.region == "Ontario"
    town_id = resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code)
    assert town_id == _town_id(conn, "Toronto", "CA", "08")


def test_resolve_town_alternate_name_alias():
    conn = _conn_with_gazetteer()
    town_id = resolve_town(conn, city="SF", region=None, country_code="US")
    assert town_id == _town_id(conn, "San Francisco", "US", "CA")


def test_resolve_town_none_when_no_country_code():
    conn = _conn_with_gazetteer()
    assert resolve_town(conn, city="San Francisco", region=None, country_code=None) is None


def test_resolve_town_none_when_no_city():
    conn = _conn_with_gazetteer()
    assert resolve_town(conn, city=None, region=None, country_code="US") is None


def test_resolve_town_none_for_venue_name():
    conn = _conn_with_gazetteer()
    assert resolve_town(conn, city="ProspectLand", region=None, country_code=None) is None


def test_resolve_town_never_matches_unscoped_ambiguous_fragment():
    conn = _conn_with_gazetteer()
    # "Ontario" alone (no country) must never resolve — could be the
    # Canadian province or a real California city named Ontario.
    assert resolve_town(conn, city="Ontario", region=None, country_code=None) is None


def test_resolve_town_same_string_variants_share_one_town_id():
    conn = _conn_with_gazetteer()
    variants = [
        "San Francisco, California, United States",
        "San Francisco, CA",
        "San Francisco, California",
    ]
    ids: set[int | None] = set()
    for raw in variants:
        p = parse_location(raw)
        ids.add(resolve_town(conn, city=p.city, region=p.region, country_code=p.country_code))
    assert ids == {_town_id(conn, "San Francisco", "US", "CA")}
