from sqlalchemy import create_engine, select

from scraper.db import metadata, towns_table
from scraper.gazetteer import _filter_alternate_names, load_towns


def _engine():
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_load_towns_populates_table_from_bundled_gazetteer():
    engine = _engine()
    with engine.begin() as conn:
        n = load_towns(conn)
        assert n > 100_000  # sanity: bundled cities1000 has ~171k rows
        count = conn.execute(select(towns_table)).fetchall()
        assert len(count) == n


def test_load_towns_finds_san_francisco_us():
    engine = _engine()
    with engine.begin() as conn:
        load_towns(conn)
        row = conn.execute(
            select(towns_table).where(
                towns_table.c.ascii_name == "San Francisco",
                towns_table.c.country_code == "US",
            )
        ).fetchone()
        assert row is not None
        assert row.admin1_code == "CA"
        assert "SF" in row.alternate_names.split(",")


def test_load_towns_is_idempotent_on_geoname_id():
    engine = _engine()
    with engine.begin() as conn:
        first = load_towns(conn)
        second = load_towns(conn)
        assert first == second
        count = conn.execute(select(towns_table)).fetchall()
        assert len(count) == first  # no duplicate rows on a second load


def test_filter_alternate_names_drops_long_and_non_ascii():
    raw = "SF,San Francisco Bay Area Municipality Extended Name,サンフランシスコ,Frisco"
    result = _filter_alternate_names(raw, ascii_name="San Francisco")
    kept = result.split(",")
    assert "SF" in kept
    assert "Frisco" in kept
    assert not any(len(alias) > 20 for alias in kept)
    assert all(alias.isascii() for alias in kept)


def test_filter_alternate_names_drops_duplicate_of_ascii_name():
    result = _filter_alternate_names("San Francisco,SF", ascii_name="San Francisco")
    assert result == "SF"
