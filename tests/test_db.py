from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Connection

from scraper.db import (
    companies_table,
    get_or_create_locations,
    job_locations_table,
    jobs_table,
    load_previous,
    locations_table,
    metadata,
    sources_table,
    towns_table,
    write_jobs,
)
from scraper.gazetteer import load_towns
from scraper.models import Job


def job(
    jid: str,
    title: str = "T",
    company: str = "X",
    locations: list[str] | None = None,
    posted_days: int | None = 0,
    first_seen: str = "2026-07-28T06:16:49+00:00",
    source: str = "workday",
    company_blurb: str = "",
) -> Job:
    return Job(
        id=jid,
        company=company,
        title=title,
        location="Montreal",
        locations=locations or ["Montreal"],
        url="https://example.com",
        posted_on="Posted Today",
        posted_days=posted_days,
        first_seen=first_seen,
        source=source,
        company_blurb=company_blurb,
    )


def _company_id(conn: Connection, name: str) -> int:
    return conn.execute(
        select(companies_table.c.id).where(companies_table.c.name == name)
    ).scalar_one()


def _source_id(conn: Connection, name: str) -> int:
    return conn.execute(select(sources_table.c.id).where(sources_table.c.name == name)).scalar_one()


def test_write_jobs_creates_tables_and_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [job("x:1"), job("x:2")]

    write_jobs(url, jobs, new_ids={"x:2"})

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = {r.id: r for r in conn.execute(select(jobs_table))}
        company_id = _company_id(conn, "X")
        source_id = _source_id(conn, "workday")

    assert set(rows) == {"x:1", "x:2"}
    assert rows["x:1"].is_new is False
    assert rows["x:2"].is_new is True
    assert rows["x:1"].posted_date == "2026-07-28"
    assert rows["x:1"].company_id == company_id
    assert rows["x:1"].source_id == source_id
    assert not hasattr(jobs_table.c, "posted_on")
    assert not hasattr(jobs_table.c, "posted_days")
    assert not hasattr(jobs_table.c, "company")
    assert not hasattr(jobs_table.c, "location")
    assert not hasattr(jobs_table.c, "locations")


def test_write_jobs_populates_companies_and_sources_without_duplicates(
    tmp_path: Path,
) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [
        job("acme:1", company="Acme", source="workday"),
        job("acme:2", company="Acme", source="workday"),
        job("globex:1", company="Globex", source="greenhouse"),
    ]

    write_jobs(url, jobs, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        company_names = {r.name for r in conn.execute(select(companies_table))}
        source_names = {r.name for r in conn.execute(select(sources_table))}

    assert company_names == {"Acme", "Globex"}
    assert source_names == {"workday", "greenhouse"}


def test_write_jobs_stores_company_blurb_on_companies_table(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [job("acme:1", company="Acme", company_blurb="Makes anvils.")]

    write_jobs(url, jobs, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        blurb = conn.execute(
            select(companies_table.c.blurb).where(companies_table.c.name == "Acme")
        ).scalar_one()

    assert blurb == "Makes anvils."


def test_write_jobs_expands_locations_into_child_table_preserving_order(
    tmp_path: Path,
) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [job("x:1", locations=["Montreal", "Toronto", "Remote"])]

    write_jobs(url, jobs, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            select(locations_table.c.name, job_locations_table.c.ordinal)
            .select_from(job_locations_table.join(locations_table))
            .where(job_locations_table.c.job_id == "x:1")
            .order_by(job_locations_table.c.ordinal)
        ).all()

    assert [(r.name, r.ordinal) for r in rows] == [
        ("Montreal", 0),
        ("Toronto", 1),
        ("Remote", 2),
    ]


def test_write_jobs_dedupes_repeated_location_names(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [
        job("x:1", locations=["Remote", "Montreal"]),
        job("x:2", locations=["Remote", "Toronto"]),
    ]

    write_jobs(url, jobs, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        names = [r.name for r in conn.execute(select(locations_table.c.name))]

    assert sorted(names) == ["Montreal", "Remote", "Toronto"]


def test_write_jobs_computes_posted_date_from_first_seen_minus_posted_days(
    tmp_path: Path,
) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    j = job("x:1", posted_days=3, first_seen="2026-07-28T06:16:49+00:00")

    write_jobs(url, [j], new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table)).one()

    assert row.posted_date == "2026-07-25"


def test_write_jobs_posted_date_null_when_posted_days_missing(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    j = job("x:1", posted_days=None)

    write_jobs(url, [j], new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table)).one()

    assert row.posted_date is None


def test_write_jobs_replaces_previous_contents(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"

    write_jobs(url, [job("x:1", company="Acme")], new_ids=set())
    write_jobs(url, [job("x:2", company="Globex")], new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        ids = {r.id for r in conn.execute(select(jobs_table))}
        company_names = {r.name for r in conn.execute(select(companies_table))}
        location_job_ids = {r.job_id for r in conn.execute(select(job_locations_table))}

    assert ids == {"x:2"}
    assert company_names == {"Globex"}
    assert location_job_ids == {"x:2"}


def test_write_jobs_handles_empty_list(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"

    write_jobs(url, [], new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        ids = list(conn.execute(select(jobs_table)))

    assert ids == []


def test_write_jobs_never_raises_on_bad_url() -> None:
    write_jobs("not-a-real://url", [job("x:1")], new_ids=set())


def test_write_jobs_dedupes_duplicate_ids_last_one_wins(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    jobs = [job("x:1", title="First"), job("x:2"), job("x:1", title="Second")]

    write_jobs(url, jobs, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = {r.id: r for r in conn.execute(select(jobs_table))}

    assert set(rows) == {"x:1", "x:2"}
    assert rows["x:1"].title == "Second"


def test_write_jobs_preserves_posted_date_across_a_round_trip(tmp_path: Path) -> None:
    """A job carried over from the previous run must keep its posting date.

    posted_days is only populated by a live scrape, so a job reconstructed
    by load_previous() has None — recomputing posted_date from it wrote NULL
    and erased a date that was already correct. Because --company merges
    every other company's jobs out of `previous`, a few single-company runs
    stripped the date off most of the pool.
    """
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(
        url,
        [job("x:1", posted_days=3, first_seen="2026-07-28T06:16:49+00:00")],
        new_ids=set(),
    )

    carried = list(load_previous(url).values())
    assert carried[0].posted_days is None  # the round-trip really does drop it
    assert carried[0].posted_date == "2026-07-25"

    # Re-writing the carried job must not lose the date.
    write_jobs(url, carried, new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table)).one()
    assert row.posted_date == "2026-07-25"


def test_write_jobs_prefers_live_scrape_date_over_carried_one(tmp_path: Path) -> None:
    """A fresh scrape still derives the date normally."""
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    j = job("x:1", posted_days=1, first_seen="2026-07-28T06:16:49+00:00")

    write_jobs(url, [j], new_ids=set())

    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table)).one()
    assert row.posted_date == "2026-07-27"


def test_get_or_create_locations_resolves_town_id_for_new_row() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as conn:
        load_towns(conn)
        ids = get_or_create_locations(conn, {"San Francisco, California, United States"})
        loc_id = ids["San Francisco, California, United States"]
        town_id = conn.execute(
            select(locations_table.c.town_id).where(locations_table.c.id == loc_id)
        ).scalar_one()
        town_name = conn.execute(
            select(towns_table.c.ascii_name).where(towns_table.c.id == town_id)
        ).scalar_one()
    assert town_name == "San Francisco"


def test_get_or_create_locations_never_overwrites_town_id_on_cache_hit() -> None:
    """A normalized_key cache hit must not recompute town_id — matching the
    same "never touch already-parsed data" contract already documented for
    city/region/country_code (see get_or_create_locations' docstring)."""
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as conn:
        load_towns(conn)
        first = get_or_create_locations(conn, {"San Francisco, CA"})
        loc_id = first["San Francisco, CA"]
        conn.execute(
            locations_table.update().where(locations_table.c.id == loc_id).values(town_id=None)
        )

        # Same normalized_key (just different casing/whitespace) — must hit
        # the existing row, not recompute and repopulate town_id.
        second = get_or_create_locations(conn, {"san francisco, ca "})
        assert second["san francisco, ca "] == loc_id
        town_id = conn.execute(
            select(locations_table.c.town_id).where(locations_table.c.id == loc_id)
        ).scalar_one()
    assert town_id is None


def test_get_or_create_locations_town_id_none_for_unmatched_location() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as conn:
        load_towns(conn)
        ids = get_or_create_locations(conn, {"ProspectLand"})
        loc_id = ids["ProspectLand"]
        town_id = conn.execute(
            select(locations_table.c.town_id).where(locations_table.c.id == loc_id)
        ).scalar_one()
    assert town_id is None


def test_write_jobs_scoped_only_replaces_its_own_companies(tmp_path: Path) -> None:
    """scope_companies must delete/replace only rows for the given
    companies — a scoped write for one shard must never touch another
    shard's already-written rows for a different company, unlike the
    default unscoped full-replace."""
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(url, [job("acme:1", company="Acme"), job("beta:1", company="Beta")], new_ids=set())

    # Scoped write for Acme only: Acme gets a fresh job, Beta is untouched.
    write_jobs(
        url,
        [job("acme:2", company="Acme")],
        new_ids={"acme:2"},
        scope_companies={"Acme"},
    )

    engine = create_engine(url)
    with engine.connect() as conn:
        ids = {r.id for r in conn.execute(select(jobs_table))}
        company_names = {r.name for r in conn.execute(select(companies_table))}

    assert ids == {"acme:2", "beta:1"}
    # Beta's own companies-table row is untouched (scoped writes never
    # delete company/source/location lookup rows, even for out-of-scope
    # companies) and Acme's row is still there too (get_or_create, not
    # deleted-then-reinserted).
    assert company_names == {"Acme", "Beta"}


def test_write_jobs_scoped_removes_company_with_zero_current_jobs(tmp_path: Path) -> None:
    """A company in scope_companies with no jobs in this write (e.g. it
    scraped to an empty listing) must still have its old rows deleted —
    same 'job leaves the pool once a scrape no longer lists it' contract as
    the unscoped path."""
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(url, [job("acme:1", company="Acme"), job("beta:1", company="Beta")], new_ids=set())

    write_jobs(url, [], new_ids=set(), scope_companies={"Acme"})

    engine = create_engine(url)
    with engine.connect() as conn:
        ids = {r.id for r in conn.execute(select(jobs_table))}

    assert ids == {"beta:1"}


def test_write_jobs_scoped_deletes_job_locations_for_its_companies_only(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(
        url,
        [
            job("acme:1", company="Acme", locations=["Montreal", "Toronto"]),
            job("beta:1", company="Beta", locations=["Paris"]),
        ],
        new_ids=set(),
    )

    write_jobs(url, [job("acme:2", company="Acme")], new_ids=set(), scope_companies={"Acme"})

    engine = create_engine(url)
    with engine.connect() as conn:
        location_job_ids = {r.job_id for r in conn.execute(select(job_locations_table))}

    assert location_job_ids == {"acme:2", "beta:1"}


def test_load_previous_scoped_to_company_names(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(url, [job("acme:1", company="Acme"), job("beta:1", company="Beta")], new_ids=set())

    scoped = load_previous(url, {"Acme"})

    assert set(scoped) == {"acme:1"}
    assert scoped["acme:1"].company == "Acme"


def test_load_previous_unscoped_returns_everything(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'jobs.db'}"
    write_jobs(url, [job("acme:1", company="Acme"), job("beta:1", company="Beta")], new_ids=set())

    everything = load_previous(url)

    assert set(everything) == {"acme:1", "beta:1"}
