"""Optional relational-database sink, selected via --database <SQLAlchemy URL>.

docs/jobs.json is always written too (the GitHub Pages dashboard has no
other way to get data), but this module is more than a passive mirror for
external consumers now: scraper/main.py's own new-job detection, first_seen
carryover, and per-job detail-fetch cache (BaseScraper._cached_detail) all
read their "previous run" state from here via load_previous(), not from
docs/jobs.json — so omitting --database disables those for that run (logged
as a warning, never fatal). SQLAlchemy's engine URL scheme picks the
dialect, so this project needs no per-database adapter code:

    postgresql+psycopg2://user:pass@host/dbname
    mysql+pymysql://user:pass@host/dbname
    sqlite:///local/path/jobs.db

Only SQLite's driver ships with the stdlib; Postgres/MySQL/etc. need their
driver package installed separately (e.g. `pip install psycopg2-binary`),
same as any SQLAlchemy consumer.

Schema is normalized rather than one flat table: `company` (214 distinct
values across ~15k jobs) and `source` (10 distinct board names) are both
low-cardinality strings repeated on every row, and `company_blurb` is a
per-company attribute that was being duplicated on every one of that
company's jobs. `location`/`locations` is a genuine one-to-many (a job can
list several offices) so it becomes a child table instead of a JSON-encoded
column — and the location text itself is also low-cardinality (thousands of
distinct strings shared across tens of thousands of postings, "Remote"/
"Toronto, Ontario" etc. repeating constantly), so it gets the same
lookup-table treatment as company/source: a `locations` table holds each
distinct string once, and `job_locations` is a pure join table of
(job_id, location_id, ordinal).

Location `name` is stored exactly as scraped, and row identity (whether a
new raw string reuses an existing row) is decided by get_or_create_locations()
via a normalized_key that only folds whitespace/casing — genuine spelling/
abbreviation variants ("Toronto" vs "Toronto, ON, CAN") are still never
silently merged into the same row, since guessing wrong there would merge
distinct places. Separately, `locations` also carries best-effort structured
fields (city/region/country_code/is_remote, parsed via
scraper.location_resolver.parse_location()) for downstream filtering — those
are additive metadata, not part of row identity.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine, make_url

from scraper.location_resolver import ParsedLocation, parse_location
from scraper.models import Job

log = logging.getLogger("scraper.db")

metadata = MetaData()

companies_table = Table(
    "companies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False, unique=True),
    Column("blurb", Text, nullable=False, server_default=""),
    # Umbrella label (e.g. "Government of Canada") for a company row whose
    # `name` is actually a narrower entity a board maps per-posting (e.g.
    # gc_jobs.py's per-department company names) — "" when `name` needs no
    # broader grouping. See Job.company_group.
    Column("group_name", String, nullable=False, server_default=""),
)

sources_table = Table(
    "sources",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False, unique=True),  # board name, e.g. "workday"
)

jobs_table = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("company_id", Integer, ForeignKey("companies.id"), nullable=False),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("title", String, nullable=False),
    Column("url", String, nullable=False),
    # Absolute calendar date the job was posted, "YYYY-MM-DD" — computed once
    # from first_seen minus posted_days at write time so it stays meaningful
    # no matter how long it sits in storage. NULL when the board exposes no
    # date at all (rippling/bamboohr): first_seen is still the fallback
    # signal for age in that case, same as the dashboard's own convention.
    # The raw posted_on ("Posted 3 Days Ago") and posted_days (relative to
    # scrape time, goes stale) are intentionally not stored — display
    # formatting belongs downstream, not in the data layer.
    Column("posted_date", String, nullable=True),
    Column("first_seen", String, nullable=False),
    Column("description", Text, nullable=False),
    Column("role_summary", Text, nullable=False),
    Column("is_new", Boolean, nullable=False),
)

# Canonical geographic identity for job locations, distinct from
# `locations` on purpose: `locations` identity is *scraped-string* identity
# (normalized_key only folds whitespace/casing — genuinely different
# spellings/formats of the same real place are deliberately never merged,
# see get_or_create_locations' docstring). `towns` identity is *geographic*
# identity, sourced from an external authority (GeoNames, see
# scraper/gazetteer.py) via its own stable geoname_id. Collapsing these two
# into one table would force a choice neither side wants: either give up
# locations' "never guess, never merge" contract, or make every gazetteer
# refresh touch scraped rows. Keeping them separate means "San Francisco",
# "San Francisco, CA", and "San Francisco, California, United States" stay
# three distinct `locations` rows (as they must) while all three can point
# at the *same* `towns` row via `locations.town_id` below — which is
# exactly the canonical identity that filtering/recommendations need and
# `locations` alone can't provide.
towns_table = Table(
    "towns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    # GeoNames' own id — lets a gazetteer refresh update a town's data in
    # place (name/lat/lon/population can all change between GeoNames
    # releases) without duplicating rows or breaking existing
    # locations.town_id references (see gazetteer.load_towns).
    Column("geoname_id", Integer, nullable=False, unique=True),
    Column("name", String, nullable=False, index=True),
    Column(
        "ascii_name", String, nullable=False, index=True
    ),  # match target: scraped strings are always ASCII/Latin, GeoNames' `name` sometimes isn't
    Column(
        "alternate_names", Text, nullable=True
    ),  # comma-joined short ASCII aliases only, e.g. "NYC" — see gazetteer.py's filtering
    Column("country_code", String, nullable=False, index=True),
    Column(
        "admin1_code", String, nullable=True, index=True
    ),  # region/state/province code; only unique *within* a country, always paired with country_code when matching
    Column("lat", Float(), nullable=False),
    Column("lon", Float(), nullable=False),
    Column("population", Integer, nullable=False, server_default="0"),
)

locations_table = Table(
    "locations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String, nullable=False, unique=True),  # raw location text, exactly as scraped
    # Structured fields, populated by get_or_create_locations() via
    # scraper.location_resolver.parse_location() at insert time. name stays
    # the row's identity/display text; these are additive metadata for
    # filtering, never used to decide whether two rows are "the same place"
    # (see get_or_create_locations' docstring below).
    Column("normalized_key", String, nullable=True, index=True),
    Column("city", String, nullable=True),
    Column("region", String, nullable=True),
    Column("country_code", String, nullable=True, index=True),
    Column("is_remote", Boolean, nullable=False, server_default="0"),
    # Resolved via scraper.town_resolver.resolve_town() at insert time only
    # (never recomputed on a normalized_key cache hit, same treatment as
    # city/region/country_code above). NULL means "unmatched" — a venue
    # name, ALL-CAPS tenant code, or genuinely ambiguous fragment (e.g.
    # "Ontario" with no country to disambiguate province vs. city) — and is
    # a permanent, correct answer for those, not a "try harder later"
    # placeholder. Callers must treat NULL as a pass-through for town-based
    # filtering, falling back to country_code, exactly like NULL
    # country_code itself already must be treated as a pass-through
    # upstream in job_pipeline's score_pool_for_user().
    Column("town_id", Integer, ForeignKey("towns.id"), nullable=True, index=True),
)

# One row per location a job lists (locations[0] is still the "primary" one,
# preserved via `ordinal`) — a pure join table; the location text itself
# lives once in `locations`, looked up via `location_id`.
job_locations_table = Table(
    "job_locations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", String, ForeignKey("jobs.id"), nullable=False),
    Column("location_id", Integer, ForeignKey("locations.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    UniqueConstraint("job_id", "ordinal"),
)


_ENGINES: dict[str, Engine] = {}


def get_engine(database_url: str) -> Engine:
    cached = _ENGINES.get(database_url)
    if cached is not None:
        return cached

    # sqlite3's driver default busy-timeout is 5s — too short for a
    # full-replace transaction across tens of thousands of rows when the
    # same file is also written to concurrently by job_pipeline's own
    # jobscraper_pool tables (see write_jobs()'s docstring). A transient
    # "database is locked" here used to be swallowed silently by
    # write_jobs()'s broad except — raising the timeout makes that failure
    # mode far less likely to begin with, on top of no longer hiding it.
    is_sqlite = make_url(database_url).get_backend_name() == "sqlite"
    connect_args = {"timeout": 60} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA cache_size = -64000")
                cursor.execute("PRAGMA temp_store = MEMORY")
                cursor.close()

    metadata.create_all(engine)
    _ensure_companies_group_name_column(engine)
    _ENGINES[database_url] = engine
    return engine


def _ensure_companies_group_name_column(engine: Engine) -> None:
    """metadata.create_all() only creates missing tables, never alters an
    existing one — so a `companies` table from before group_name existed
    (e.g. prod's live scraper.db) needs this explicit backfill or every
    read/write against that column below would fail with "no such column."
    """
    inspector = inspect(engine)
    existing = {col["name"] for col in inspector.get_columns("companies")}
    if "group_name" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE companies ADD COLUMN group_name VARCHAR NOT NULL DEFAULT ''")
            )


def checkpoint_wal(database_url: str) -> None:
    """Best-effort PASSIVE WAL checkpoint after a write, for sqlite URLs only
    (a no-op for other backends). PASSIVE checkpoints as much of the WAL as
    it can without blocking or forcing out concurrent readers/writers —
    unlike wal_autocheckpoint (set from job_pipeline's Node side, see
    jobby/classes/DB.ts), which can't run to completion while any
    transaction is still open, this runs after write_jobs() has already
    closed its own transactions, so it's a direct backstop against the WAL
    growing unbounded (387MB observed in prod before this existed) rather
    than relying solely on auto-checkpoint's opportunistic timing. Failure
    here (e.g. another writer briefly holding the file) is logged and
    swallowed — it's cleanup, not part of the write's own success/failure
    contract.
    """
    if make_url(database_url).get_backend_name() != "sqlite":
        return
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
    except Exception:
        log.warning("WAL checkpoint failed for %s (non-fatal)", _redacted(database_url))


def load_previous(database_url: str, company_names: set[str] | None = None) -> dict[str, Job]:
    """The last run's full job set, keyed by Job.id — main.py's `previous`
    for diffing/first_seen-carryover/detail-fetch-caching, read from
    whatever write_jobs() last wrote here instead of docs/jobs.json.

    company_names, when given, scopes both the query and the returned dict
    to just those companies' previously stored jobs — the sharded-run path
    (main.py's --shard-size) uses this so a shard's peak memory is bounded
    by that shard's own previous+current job count, not the whole pool's.
    None (the default) loads everything, same as before this parameter
    existed.

    posted_on/posted_days come back empty/None on every reconstructed Job:
    this schema only stores the derived posted_date, and neither raw field
    survives a round-trip.

    That made posted_date itself load-bearing. It used to be recomputed from
    posted_days on every write, so a carried-over job — posted_days=None by
    construction — wrote NULL and erased the date it already had. Since
    --company merges every other company's jobs out of `previous`, a handful
    of single-company runs was enough to strip the date off most of the
    pool. The stored posted_date is therefore read back here and preferred
    by _posted_date().

    Best-effort like write_jobs(): a missing table, bad URL, or connection
    error just means an empty previous (this run treats everything as new),
    not a crash — matching every other optional integration in this
    pipeline. Call sites should still warn the operator when this returns
    {} unexpectedly (e.g. because --database was never passed), since an
    empty previous silently disables new-job detection and the detail-fetch
    cache for that run.
    """
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            companies_by_id = {row.id: row for row in conn.execute(select(companies_table))}
            sources_by_id = {row.id: row for row in conn.execute(select(sources_table))}

            jobs_query = select(jobs_table)
            if company_names is not None:
                scoped_company_ids = {
                    cid for cid, row in companies_by_id.items() if row.name in company_names
                }
                jobs_query = jobs_query.where(jobs_table.c.company_id.in_(scoped_company_ids))
            job_rows = list(conn.execute(jobs_query))
            job_ids = {row.id for row in job_rows}
            if company_names is not None:
                locations_by_job: dict[str, list[str]] = {}
                if job_ids:
                    loc_query = (
                        select(job_locations_table.c.job_id, locations_table.c.name)
                        .join(
                            locations_table,
                            job_locations_table.c.location_id == locations_table.c.id,
                        )
                        .where(job_locations_table.c.job_id.in_(job_ids))
                        .order_by(job_locations_table.c.ordinal)
                    )
                    for row in conn.execute(loc_query):
                        locations_by_job.setdefault(row.job_id, []).append(row.name)
            else:
                locations_by_id = {
                    row.id: row.name for row in conn.execute(select(locations_table))
                }
                locations_by_job = {}
                for row in conn.execute(
                    select(job_locations_table).order_by(job_locations_table.c.ordinal)
                ):
                    name = locations_by_id.get(row.location_id)
                    if name is not None:
                        locations_by_job.setdefault(row.job_id, []).append(name)

            previous: dict[str, Job] = {}
            for row in job_rows:
                company = companies_by_id.get(row.company_id)
                source = sources_by_id.get(row.source_id)
                locations = locations_by_job.get(row.id, [])
                previous[row.id] = Job(
                    id=row.id,
                    company=company.name if company else "",
                    title=row.title,
                    location=locations[0] if locations else "",
                    url=row.url,
                    posted_on="",
                    source=source.name if source else "",
                    first_seen=row.first_seen,
                    locations=locations,
                    posted_days=None,
                    posted_date=row.posted_date,
                    description=row.description,
                    role_summary=row.role_summary,
                    company_blurb=company.blurb if company else "",
                    company_group=company.group_name if company else "",
                )
        return previous
    except Exception:
        log.exception(
            "Failed to load previous state from %s — treating as first run",
            _redacted(database_url),
        )
        return {}


def _posted_date(job: Job) -> str | None:
    """first_seen minus posted_days, as "YYYY-MM-DD". None if either input
    is missing/unparseable (date-less boards, e.g. rippling/bamboohr).

    A date already carried on the job wins. posted_days is only populated by
    a live scrape, so for a job reconstructed from the previous run (see
    load_previous) this would otherwise recompute to None and erase a
    perfectly good date — which, because --company merges every other
    company's jobs from `previous`, wiped the date off most of the pool.
    """
    if job.posted_date:
        return job.posted_date
    if job.posted_days is None or not job.first_seen:
        return None
    try:
        seen = datetime.fromisoformat(job.first_seen)
    except ValueError:
        return None
    return (seen - timedelta(days=job.posted_days)).date().isoformat()


def _get_or_create_ids(conn: Connection, table: Table, names: set[str]) -> dict[str, int]:
    """Look up existing rows by `name`, insert whatever's missing, return the
    full {name: id} map. Two-pass (select-missing, insert, re-select) rather
    than a single upsert so the same helper works across SQLAlchemy dialects
    without dialect-specific ON CONFLICT syntax.

    Used for companies/sources, where raw-string identity is correct (a
    company/board name is either an exact match or a genuinely different
    one — no casing/whitespace variance problem has been observed there).
    `locations` uses get_or_create_locations() below instead, since job-board
    location strings vary in casing/whitespace far more than company/source
    names ever have.
    """
    if not names:
        return {}
    existing: dict[str, int] = {
        row.name: row.id
        for row in conn.execute(select(table.c.name, table.c.id).where(table.c.name.in_(names)))
    }
    missing = names - existing.keys()
    if missing:
        conn.execute(table.insert(), [{"name": name} for name in missing])
        existing.update(
            (row.name, row.id)
            for row in conn.execute(
                select(table.c.name, table.c.id).where(table.c.name.in_(missing))
            )
        )
    return existing


def get_or_create_locations(conn: Connection, names: dict[str, str | None]) -> dict[str, int]:
    """Look up existing `locations` rows by normalized_key (trim+casefold+
    collapse-whitespace of the raw string — see location_resolver.py), not
    by raw `name`, so "Toronto, Ontario, Canada" and "TORONTO, Ontario,
    Canada" resolve to the same row instead of creating a duplicate.

    A match reuses the existing row's id as-is: its stored `name` (display
    casing) and structured columns (city/region/country_code/is_remote/
    town_id) are NOT overwritten, so re-scraping never churns already-parsed
    data even if location_resolver.py's parsing logic improves later —
    that's a separate, explicit backfill (scripts/normalize_existing_locations.py
    for city/region/country_code/is_remote, backfill_town_ids.py for
    town_id), not an implicit side effect of every write. A new raw string
    (no normalized_key match) inserts a new row with `name` plus its freshly
    parsed structured columns, town_id included — resolved the same way the
    one-off backfill resolves it for existing rows (see
    scraper.town_resolver.resolve_town), just for this one new row instead
    of the whole table.

    `names` maps each raw location string to a `default_country` (or None)
    — see parse_location's own docstring for what this does and doesn't
    override. Since a `locations` row is shared across every company whose
    jobs happen to use the identical raw string (row identity is per-
    string, not per-company), the SAME raw string could in principle arrive
    here with two different companies' defaults; whichever happens to be
    present in this dict wins for that string (the caller, write_jobs(),
    resolves that ambiguity by building this dict in job iteration order
    and never overwriting an existing key — first company wins, the same
    tie-break already used elsewhere in this module for a duplicate Job.id
    or company_blurb). Only matters for a default_country actually being
    set for more than one company on an identical raw string, an edge case
    expected to be rare.

    Returns {raw_name: id} for every input name, keyed by the exact raw
    string passed in (mirrors _get_or_create_ids' return shape) — so callers
    joining against job.locations (raw strings) don't need to know which raw
    string ended up sharing a row with which.
    """
    if not names:
        return {}

    parsed_by_name = {
        name: parse_location(name, default_country=default_country)
        for name, default_country in names.items()
    }
    keys = {p.normalized_key for p in parsed_by_name.values()}

    existing_by_key: dict[str, int] = {
        row.normalized_key: row.id
        for row in conn.execute(
            select(locations_table.c.normalized_key, locations_table.c.id).where(
                locations_table.c.normalized_key.in_(keys)
            )
        )
        if row.normalized_key is not None
    }

    missing_keys = keys - existing_by_key.keys()
    if missing_keys:
        # Local import to avoid a circular import at module load time:
        # town_resolver.py itself imports towns_table from this module, so
        # importing resolve_town back at db.py's module scope would cycle.
        from scraper.town_resolver import resolve_town

        # One raw string per missing key — the first one encountered in
        # `names` becomes that key's stored display text.
        to_insert: dict[str, ParsedLocation] = {}
        for parsed in parsed_by_name.values():
            if parsed.normalized_key in missing_keys and parsed.normalized_key not in to_insert:
                to_insert[parsed.normalized_key] = parsed
        conn.execute(
            locations_table.insert(),
            [
                {
                    "name": p.raw,
                    "normalized_key": p.normalized_key,
                    "city": p.city,
                    "region": p.region,
                    "country_code": p.country_code,
                    "is_remote": p.is_remote,
                    "town_id": resolve_town(
                        conn, city=p.city, region=p.region, country_code=p.country_code
                    ),
                }
                for p in to_insert.values()
            ],
        )
        existing_by_key.update(
            (row.normalized_key, row.id)
            for row in conn.execute(
                select(locations_table.c.normalized_key, locations_table.c.id).where(
                    locations_table.c.normalized_key.in_(missing_keys)
                )
            )
        )

    return {name: existing_by_key[parsed.normalized_key] for name, parsed in parsed_by_name.items()}


# Row count per chunked insert transaction (jobs_table / job_locations_table
# in write_jobs()). Keeps each transaction's writer-lock hold to a fraction
# of a second to a couple seconds instead of one transaction spanning the
# full multi-thousand-row write — see write_jobs()'s docstring for why this
# replaced a single whole-write transaction.
_WRITE_CHUNK_SIZE = 750


def _insert_in_chunks(engine: Engine, table: Table, rows: Sequence[Mapping[str, object]]) -> None:
    """Insert `rows` into `table` across multiple short transactions of up
    to _WRITE_CHUNK_SIZE rows each, instead of one transaction for the whole
    list — see write_jobs()'s docstring."""
    for start in range(0, len(rows), _WRITE_CHUNK_SIZE):
        chunk = rows[start : start + _WRITE_CHUNK_SIZE]
        with engine.begin() as conn:
            conn.execute(table.insert(), chunk)


def write_jobs(
    database_url: str,
    jobs: list[Job],
    new_ids: set[str],
    *,
    scope_companies: set[str] | None = None,
) -> bool:
    """Replace the current snapshot's contents with `jobs`.

    scope_companies=None (the default): full-replace semantics across every
    table — every companies/sources/locations/jobs/job_locations row is
    deleted and reinserted from `jobs`, so the tables never accumulate jobs
    no longer in the pool. This is the original, whole-pool behavior.

    scope_companies=<names>: a sharded write (main.py's --shard-size path).
    Only jobs/job_locations rows belonging to those companies are deleted
    before reinserting `jobs` — company/source/location lookup rows are
    left alone (get_or_create semantics: looked up or inserted, never
    deleted), since a scoped write only knows about its own shard's
    content and wiping those shared lookup tables would break FK
    references still held by every other shard's already-written rows.
    Companies in scope_companies that no longer have any current job (e.g.
    a company scraped to zero postings this run) still get their old rows
    deleted with nothing to replace them, same "job leaves the pool once a
    scrape no longer lists it" contract as the whole-pool path.

    The delete, the company/source/location lookups, and the jobs/
    job_locations inserts each run in their own short transaction rather
    than one transaction spanning the whole write (the inserts are further
    split into _WRITE_CHUNK_SIZE-row batches, each its own transaction) —
    a full unscoped write is tens of thousands of rows, and holding a
    single SQLite writer lock for the whole thing (multi-minute, confirmed
    in prod) starved concurrent readers on other tables in the same file
    (data/app.db) hard enough to fail their queries outright (see
    job_pipeline's jobby/utils/db/busy-retry-wrap.ts, GitHub issue #38).
    This trades strict all-or-nothing atomicity for bounded per-transaction
    lock hold: a concurrent reader can now observe a transiently smaller
    pool mid-write (old rows already deleted, new rows not all inserted
    yet) instead of an instantaneous swap — acceptable since every known
    reader (job_pipeline's JobScraperFetcher, the Node pool reads) already
    tolerates "pool between scrape runs" as a normal state, and this is a
    strict improvement over a multi-minute exclusive lock.

    Returns True on success, False on failure — the caller (scraper/main.py's
    run()) must check this and fail the run's exit code accordingly. This
    used to swallow every failure and return None, matching the "best-effort,
    never fatal" policy used elsewhere in this pipeline (AI summaries, board
    scrapers) — but --database is the *only* sink now (docs/jobs.json is
    gone), so a silently swallowed write failure meant a run could report
    success while persisting nothing. Confirmed in practice 2026-08-14: a
    5s default SQLite busy-timeout (see get_engine) plus concurrent access
    from job_pipeline's own jobscraper_pool tables in the same file caused
    exactly this — main.py's --jobscraper-pipeline saw exit code 0 and
    proceeded to ingest/parse against unchanged data for over a week.

    Since the write is no longer one transaction, a failure partway through
    (e.g. mid-chunk) leaves whatever chunks already committed in place
    rather than rolling back the entire write, unlike before — the
    exception log below reports how far the write got so this partial
    state is distinguishable from "wrote nothing."

    A handful of boards occasionally produce a non-unique Job.id (their
    upstream requisition label collides across postings) — last one wins,
    same as `jobs` dict-keyed by id would behave, rather than letting the
    table's primary key reject the whole batch.
    """
    start = time.monotonic()
    stage = "setup"
    try:
        engine = get_engine(database_url)
        by_id = {job.id: job for job in jobs}
        if len(by_id) != len(jobs):
            log.warning(
                "%d duplicate job ids collapsed before write (last one wins)",
                len(jobs) - len(by_id),
            )
        unique_jobs = list(by_id.values())

        stage = "delete"
        with engine.begin() as conn:
            # Child-to-parent delete order (job_locations -> jobs[-> locations/
            # companies/sources when unscoped]) to respect FK constraints on
            # databases that enforce them.
            if scope_companies is None:
                conn.execute(job_locations_table.delete())
                conn.execute(jobs_table.delete())
                conn.execute(companies_table.delete())
                conn.execute(sources_table.delete())
                conn.execute(locations_table.delete())
            else:
                scoped_company_ids = select(companies_table.c.id).where(
                    companies_table.c.name.in_(scope_companies)
                )
                scoped_job_ids = select(jobs_table.c.id).where(
                    jobs_table.c.company_id.in_(scoped_company_ids)
                )
                conn.execute(
                    job_locations_table.delete().where(
                        job_locations_table.c.job_id.in_(scoped_job_ids)
                    )
                )
                conn.execute(
                    jobs_table.delete().where(jobs_table.c.company_id.in_(scoped_company_ids))
                )

        stage = "lookups"
        with engine.begin() as conn:
            company_blurbs = {job.company: job.company_blurb for job in unique_jobs}
            company_groups = {job.company: job.company_group for job in unique_jobs}
            company_ids = _get_or_create_ids(conn, companies_table, set(company_blurbs))
            for name, blurb in company_blurbs.items():
                if blurb:
                    conn.execute(
                        companies_table.update()
                        .where(companies_table.c.id == company_ids[name])
                        .values(blurb=blurb)
                    )
            for name, group in company_groups.items():
                if group:
                    conn.execute(
                        companies_table.update()
                        .where(companies_table.c.id == company_ids[name])
                        .values(group_name=group)
                    )
            source_ids = _get_or_create_ids(
                conn, sources_table, {job.source for job in unique_jobs}
            )
            # Dict, not set: carries each name's default_country through to
            # get_or_create_locations() (see that function's own docstring
            # for the first-company-wins tie-break when the same raw string
            # arrives with two different companies' defaults). Built by
            # iterating unique_jobs in order and never overwriting an
            # existing key, so the first job encountered for a given raw
            # string is the one whose default_country wins — same
            # convention already used for by_id/company_blurbs above.
            location_names: dict[str, str | None] = {}
            for job in unique_jobs:
                for loc in job.locations:
                    if loc not in location_names:
                        location_names[loc] = job.default_country or None
            location_ids = get_or_create_locations(conn, location_names)

        stage = "insert jobs"
        if unique_jobs:
            job_rows = [
                {
                    "id": job.id,
                    "company_id": company_ids[job.company],
                    "source_id": source_ids[job.source],
                    "title": job.title,
                    "url": job.url,
                    "posted_date": _posted_date(job),
                    "first_seen": job.first_seen,
                    "description": job.description,
                    "role_summary": job.role_summary,
                    "is_new": job.id in new_ids,
                }
                for job in unique_jobs
            ]
            _insert_in_chunks(engine, jobs_table, job_rows)

            stage = "insert job_locations"
            location_rows = [
                {"job_id": job.id, "location_id": location_ids[loc], "ordinal": i}
                for job in unique_jobs
                for i, loc in enumerate(job.locations)
            ]
            if location_rows:
                _insert_in_chunks(engine, job_locations_table, location_rows)

        elapsed = time.monotonic() - start
        log.info(
            "Wrote %d jobs to %s in %.2fs",
            len(unique_jobs),
            _redacted(database_url),
            elapsed,
        )
        return True
    except Exception:
        elapsed = time.monotonic() - start
        log.exception(
            "Database write failed for %s during '%s' after %.2fs — any earlier "
            "stage/chunk already committed remains in place (writes are no "
            "longer a single all-or-nothing transaction, see write_jobs() docstring)",
            _redacted(database_url),
            stage,
            elapsed,
        )
        return False


def update_role_summary(database_url: str, job_id: str, role_summary: str) -> bool:
    """Patch a single job's role_summary in place after write_jobs() already
    committed the pool — see scraper/main.py's run(), which now writes the
    pool first and requests AI summaries afterward so a slow/failing LLM
    provider can no longer delay the pool write itself. A single-row UPDATE
    rather than another full-table write; a no-op (returns True) if the job
    isn't present, which can legitimately happen if a later shard's/run's
    write already replaced it by the time this patch lands.

    Best-effort like write_jobs() — logs and returns False on failure rather
    than raising, since a missed summary patch is not worth losing the run
    over (unlike the pool write itself).
    """
    try:
        engine = get_engine(database_url)
        with engine.begin() as conn:
            conn.execute(
                jobs_table.update()
                .where(jobs_table.c.id == job_id)
                .values(role_summary=role_summary)
            )
        return True
    except Exception:
        log.exception("role_summary patch failed for job %s", job_id)
        return False


def _redacted(database_url: str) -> str:
    """Strip credentials from a connection URL before it hits the logs."""
    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return "<database>"
