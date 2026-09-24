import json
import os
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

import scraper.main as main_module
from scraper.boards.base import BaseScraper
from scraper.config_types import CompanyConfig
from scraper.db import jobs_table, locations_table
from scraper.models import Job


def write_config(path: Path, companies: list[CompanyConfig]) -> None:
    path.write_text(
        json.dumps({"companies": companies}),
        encoding="utf-8",
    )


class StubScraper(BaseScraper):
    """Registered under a fake board name; returns whatever jobs are queued for it."""

    def fetch_jobs(self) -> list[Job]:
        return jobs_by_company_state[self.company["name"]]


jobs_by_company_state: dict[str, list[Job]] = {}


def job(
    company: str,
    jid: str,
    title: str = "Senior Staff Manager Intern",
    posted_days: int | None = None,
) -> Job:
    """Deliberately blacklist-shaped title — must survive since filtering is gone."""
    return Job(
        id=jid,
        company=company,
        title=title,
        location="Paris, France",
        locations=["Paris, France"],
        url="https://example.com",
        posted_on="Posted Today",
        source="stub",
        posted_days=posted_days,
    )


class CountingWriteJobsStub:
    """A write_jobs-shaped stub that tracks how many times it was called."""

    def __init__(self, success: bool) -> None:
        self.success = success
        self.calls = 0

    def __call__(
        self,
        database: str,
        jobs: list[Job],
        new_ids: set[str],
        *,
        scope_companies: set[str] | None = None,
    ) -> bool:
        self.calls += 1
        return self.success


class FlakyWriteJobsStub:
    """A write_jobs-shaped stub that fails its first `fail_times` calls, then
    succeeds — simulates a transient SQLITE_BUSY that clears up on retry."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def __call__(
        self,
        database: str,
        jobs: list[Job],
        new_ids: set[str],
        *,
        scope_companies: set[str] | None = None,
    ) -> bool:
        self.calls += 1
        return self.calls > self.fail_times


def setup_run(
    tmp_path: Path,
    companies: list[CompanyConfig],
    jobs_by_company: dict[str, list[Job]],
) -> tuple[str, main_module.RunDeps]:
    global jobs_by_company_state
    jobs_by_company_state = jobs_by_company
    config_path = tmp_path / "config.json"
    write_config(config_path, companies)
    deps = main_module.RunDeps(
        config_path=config_path,
        scrapers={"stub": StubScraper},
    )
    return f"sqlite:///{tmp_path / 'jobs.db'}", deps


def db_job_ids(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        return {r.id for r in conn.execute(select(jobs_table))}


def db_role_summary(db_url: str, job_id: str) -> str | None:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table).where(jobs_table.c.id == job_id)).fetchone()
        return row.role_summary if row else None


def db_first_seen_and_posted_date(db_url: str, job_id: str) -> tuple[str | None, str | None]:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table).where(jobs_table.c.id == job_id)).fetchone()
        assert row is not None
        return row.first_seen, row.posted_date


def test_full_run_stores_every_job_unfiltered(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    result = main_module.run(database=db_url, deps=deps)

    assert result == 0
    # A blacklisted-looking, all-foreign-location job survives — no storage filter.
    assert db_job_ids(db_url) == {"acme:1"}


def test_full_run_without_database_or_limit_errors(tmp_path: Path) -> None:
    _db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    result = main_module.run(deps=deps)  # no database=, no limit=

    # --database is the only sink now — without it (and without --limit,
    # which exempts the smoke-test path) there'd be nowhere to write the
    # results, so this must fail fast rather than silently scrape for nothing.
    assert result == 1


def test_company_scoped_run_merges_into_existing_snapshot(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
        },
    )

    # Seed a full previous state (in --database, the --company merge's
    # source) with both companies.
    assert main_module.run(database=db_url, deps=deps) == 0

    # Now Acme has a fresh listing; Beta isn't re-scraped this run.
    jobs_by_company_state["Acme"] = [job("Acme", "acme:2")]
    result = main_module.run(company="Acme", database=db_url, deps=deps)

    assert result == 0
    # Beta's job is untouched; Acme's old job is gone, replaced by the fresh one.
    assert db_job_ids(db_url) == {"beta:1", "acme:2"}


def test_company_scoped_run_requires_database(tmp_path: Path) -> None:
    _db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    result = main_module.run(company="Acme", deps=deps)  # no database=

    assert result == 1


def test_company_scoped_run_with_limit_does_not_require_database(tmp_path: Path) -> None:
    _db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    # --limit is a smoke test — skips the --database requirement too.
    result = main_module.run(company="Acme", limit=1, deps=deps)

    assert result == 0


def test_unknown_company_name_errors(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": []},
    )

    assert main_module.run(company="Nonexistent", database=db_url, deps=deps) == 1


def test_database_flag_mirrors_snapshot_into_sql_db(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    result = main_module.run(database=db_url, deps=deps)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1"}


def test_default_country_config_fills_unresolved_location_country_code(
    tmp_path: Path,
) -> None:
    # "00146 - Puyallup Dialysis" carries no country signal on its own
    # (verified: resolve_country_from_location returns None for it) — a
    # confirmed single-country employer's config.json "default_country"
    # must reach the stored locations row as the fallback, denormalized
    # by main.py's run() the same way company_blurb already is.
    davita_job = Job(
        id="davita:1",
        company="DaVita",
        title="RN",
        location="00146 - Puyallup Dialysis",
        locations=["00146 - Puyallup Dialysis"],
        url="https://example.com",
        posted_on="Posted Today",
        source="stub",
    )
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "DaVita", "board": "stub", "default_country": "US"}],
        jobs_by_company={"DaVita": [davita_job]},
    )

    result = main_module.run(database=db_url, deps=deps)

    assert result == 0
    engine = create_engine(db_url)
    with engine.connect() as conn:
        country_code = conn.execute(
            select(locations_table.c.country_code).where(
                locations_table.c.name == "00146 - Puyallup Dialysis"
            )
        ).scalar_one()
    assert country_code == "US"


def test_database_write_skipped_when_limit_set(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    db_path = tmp_path / "jobs.db"

    result = main_module.run(limit=1, database=db_url, deps=deps)

    assert result == 0
    assert not db_path.exists()


def _noop_sleep(_seconds: float) -> None:
    pass


def test_write_failure_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """write_jobs() now reports success/failure explicitly instead of
    swallowing every exception — confirmed in practice 2026-08-14 that a
    silently-swallowed write failure let --jobscraper-pipeline see exit 0
    and proceed against unchanged data. run() must propagate a real failure
    into a non-zero exit code.

    A persistent (non-transient) failure exhausts run()'s own retry loop
    (see GitHub issue #38 — a purely transient SQLITE_BUSY shouldn't discard
    a whole run's results) before giving up, so write_jobs is called
    multiple times, not just once."""
    monkeypatch.setattr(main_module.time, "sleep", _noop_sleep)
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    write_calls = CountingWriteJobsStub(success=False)
    deps.write_jobs = write_calls

    result = main_module.run(database=db_url, deps=deps)

    assert write_calls.calls == 5
    assert result == 1


def test_write_failure_retries_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient write failure (e.g. SQLITE_BUSY from concurrent scheduler
    jobs against the shared scraper.db, see GitHub issue #38) should not
    discard the run's results if a later retry succeeds."""
    monkeypatch.setattr(main_module.time, "sleep", _noop_sleep)
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    write_calls = FlakyWriteJobsStub(fail_times=2)
    deps.write_jobs = write_calls

    result = main_module.run(database=db_url, deps=deps)

    assert write_calls.calls == 3
    assert result == 0


def test_write_failure_recovers_on_a_late_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the retry budget itself: with write_attempts
    raised from 3 to 5 (see main.py's _run_batch — under prod's observed
    40-95s writes during memory/swap pressure, 3 attempts at 2s/4s backoff
    left too little room for contention to clear), a write that only
    recovers on attempt 4 or 5 must now succeed where it previously
    wouldn't have gotten the chance to."""
    monkeypatch.setattr(main_module.time, "sleep", _noop_sleep)
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    write_calls = FlakyWriteJobsStub(fail_times=4)
    deps.write_jobs = write_calls

    result = main_module.run(database=db_url, deps=deps)

    assert write_calls.calls == 5
    assert result == 0


def test_interrupted_run_saves_completed_companies_and_keeps_others_unchanged(
    tmp_path: Path,
) -> None:
    """Ctrl-C partway through a full run must not lose whatever already
    finished, and must not silently delete companies that hadn't been
    reached yet from the pool. Simulates: Acme finishes normally, Beta's
    scrape raises KeyboardInterrupt (the point where a real Ctrl-C would
    land mid-request) — Zeta, already in a previous snapshot, was never
    even reached this run.
    """
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
            {"name": "Zeta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
            "Zeta": [job("Zeta", "zeta:1")],
        },
    )

    # Seed a previous snapshot so Zeta (never reached this run) has
    # something to be carried forward from, rather than trivially absent.
    main_module.run(database=db_url, deps=deps)

    class InterruptingScraper(StubScraper):
        def fetch_jobs(self) -> list[Job]:
            if self.company["name"] == "Beta":
                raise KeyboardInterrupt
            return super().fetch_jobs()

    deps.scrapers = {"stub": InterruptingScraper}
    # concurrency=1 makes ordering deterministic: Acme completes, then
    # Beta's KeyboardInterrupt fires before Zeta is ever submitted.
    result = main_module.run(database=db_url, concurrency=1, deps=deps)

    assert result == 130  # 128+SIGINT — distinguishes interrupted-but-saved from clean/failed
    ids = db_job_ids(db_url)
    assert "acme:1" in ids  # completed before the interrupt — saved
    assert "zeta:1" in ids  # never reached this run — carried forward from previous snapshot
    # Beta's own scrape raised before producing a job, so nothing new to
    # carry for it either way — this assertion documents that, not a
    # requirement that beta:1 must be absent.


def test_concurrency_flag_is_accepted_and_threaded_through(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
        },
    )

    result = main_module.run(concurrency=1, database=db_url, deps=deps)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1", "beta:1"}


def test_concurrency_flag_defaults_when_omitted(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    result = main_module.run(database=db_url, deps=deps)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1"}


def test_llm_provider_flag_sets_env_for_summarize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--llm-provider still sets LLM_PROVIDER — kept for
    scraper/backfill_blurbs.py's separate one-time company-blurb path
    (scraper/summarize.py), even though main.py's own scrape no longer
    calls summarize_role() per job."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    result = main_module.run(llm_provider="ollama", database=db_url, deps=deps)

    assert result == 0
    assert os.environ["LLM_PROVIDER"] == "ollama"


def test_llm_provider_omitted_leaves_env_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    result = main_module.run(database=db_url, deps=deps)

    assert result == 0
    assert "LLM_PROVIDER" not in os.environ


def test_role_summary_carried_over_for_already_known_job(tmp_path: Path) -> None:
    """role_summary is no longer generated during scrape (see main.py's run())
    — it's populated out-of-band by job_pipeline's backlog batch inference,
    patched in directly via update_role_summary. Every board scraper builds
    a fresh Job() each run (role_summary="" by dataclass default), so
    without carrying the previous run's role_summary forward for
    already-known jobs, that out-of-band value would be silently overwritten
    with "" on every subsequent scrape."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    assert main_module.run(database=db_url, deps=deps) == 0

    # Simulates job_pipeline's backlog inference patching in a summary
    # out-of-band, the same way it happens against the real database.
    deps.update_role_summary(db_url, "acme:1", "Builds great things.")
    assert db_role_summary(db_url, "acme:1") == "Builds great things."

    # Second run: same job id, but a FRESH Job object (role_summary="" by
    # default) — exactly what every real board scraper produces, since none
    # of them read role_summary back from anywhere.
    jobs_by_company_state["Acme"] = [job("Acme", "acme:1")]

    assert main_module.run(database=db_url, deps=deps) == 0

    # The out-of-band summary must survive, not get overwritten with "".
    assert db_role_summary(db_url, "acme:1") == "Builds great things."


def test_new_job_gets_first_seen_stamped_and_posted_date_derived(tmp_path: Path) -> None:
    """Every board scraper builds a fresh Job() each run (first_seen="" by
    dataclass default). Without main.py stamping first_seen for genuinely
    new jobs, db.py's _posted_date() can never derive a real posted_date
    from posted_days, even when the board supplied one — and since
    first_seen/posted_date round-trip unchanged via load_previous(), the
    job would stay dateless forever, not just on this first run."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1", posted_days=3)]},
    )

    assert main_module.run(database=db_url, deps=deps) == 0

    first_seen, posted_date = db_first_seen_and_posted_date(db_url, "acme:1")
    assert first_seen  # non-empty — the whole point of the fix
    assert posted_date is not None


def test_first_seen_survives_unchanged_across_runs(tmp_path: Path) -> None:
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1", posted_days=3)]},
    )

    assert main_module.run(database=db_url, deps=deps) == 0
    first_seen_1, posted_date_1 = db_first_seen_and_posted_date(db_url, "acme:1")

    # Second run: same job id, fresh Job object — exactly what a real board
    # scraper produces (first_seen="" again, since no board reads it back).
    jobs_by_company_state["Acme"] = [job("Acme", "acme:1", posted_days=3)]
    assert main_module.run(database=db_url, deps=deps) == 0
    first_seen_2, posted_date_2 = db_first_seen_and_posted_date(db_url, "acme:1")

    assert first_seen_2 == first_seen_1
    assert posted_date_2 == posted_date_1


def test_shard_size_produces_same_result_as_unsharded(tmp_path: Path) -> None:
    """--shard-size must be purely a memory/isolation optimization — the
    final pool contents for a full run must be identical whether it's done
    as one batch or several."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
            {"name": "Gamma", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
            "Gamma": [job("Gamma", "gamma:1")],
        },
    )

    result = main_module.run(database=db_url, deps=deps, shard_size=1)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1", "beta:1", "gamma:1"}


def test_shard_size_scopes_write_to_its_own_companies(tmp_path: Path) -> None:
    """A sharded write must only ever delete/replace rows for companies in
    its own shard — a later shard's write must never touch an earlier
    shard's already-committed rows for a *different* company."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
        },
    )

    assert main_module.run(database=db_url, deps=deps, shard_size=1) == 0
    assert db_job_ids(db_url) == {"acme:1", "beta:1"}

    # Re-run with Acme now scraping to zero jobs (e.g. the board returned an
    # empty listing) — only Acme's rows should be removed; Beta's shard
    # never re-runs in this second call, so its row must survive untouched.
    jobs_by_company_state["Acme"] = []
    assert main_module.run(database=db_url, deps=deps, shard_size=1) == 0
    assert db_job_ids(db_url) == {"beta:1"}


def test_shard_failure_does_not_lose_other_shards_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of sharding: one shard's write failure must not
    discard another shard's already-committed results, unlike the original
    single-transaction-for-everything behavior."""
    monkeypatch.setattr(time, "sleep", _noop_sleep)
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
        },
    )

    real_write_jobs = deps.write_jobs

    def fail_beta_only(
        database: str,
        jobs: list[Job],
        new_ids: set[str],
        *,
        scope_companies: set[str] | None = None,
    ) -> bool:
        if scope_companies == {"Beta"}:
            return False
        return real_write_jobs(database, jobs, new_ids, scope_companies=scope_companies)

    deps.write_jobs = fail_beta_only

    result = main_module.run(database=db_url, deps=deps, shard_size=1)

    # Overall run reports failure (Beta's shard genuinely failed)...
    assert result == 1
    # ...but Acme's shard, which succeeded, is still in the pool.
    assert "acme:1" in db_job_ids(db_url)
    assert "beta:1" not in db_job_ids(db_url)


def test_shard_size_omitted_is_a_single_unscoped_shard(tmp_path: Path) -> None:
    """No --shard-size (or a size >= company count) must behave exactly
    like the original unsharded run: one batch, unscoped full-replace
    write."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "Beta": [job("Beta", "beta:1")],
        },
    )
    write_calls = CountingWriteJobsStub(success=True)
    deps.write_jobs = write_calls

    assert main_module.run(database=db_url, deps=deps) == 0
    assert write_calls.calls == 1  # one batch, not one per company

    write_calls_oversized = CountingWriteJobsStub(success=True)
    deps.write_jobs = write_calls_oversized
    assert main_module.run(database=db_url, deps=deps, shard_size=100) == 0
    assert write_calls_oversized.calls == 1  # shard_size >= company count collapses to one batch


def test_company_scoped_run_ignores_shard_size(tmp_path: Path) -> None:
    """--company is always its own single unscoped batch — --shard-size
    only applies to a full run across every configured company."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    write_calls = CountingWriteJobsStub(success=True)
    deps.write_jobs = write_calls

    result = main_module.run(company="Acme", database=db_url, deps=deps, shard_size=1)

    assert result == 0
    assert write_calls.calls == 1


def _company(name: str) -> CompanyConfig:
    return {"name": name, "board": "stub"}


def test_shard_buckets_by_job_count_not_company_count() -> None:
    """The whole point of job-count-aware sharding: company job counts are
    wildly skewed in the real pool (confirmed on prod 2026-09-22 — a
    100-company shard that happened to include several large employers
    scraped 41k jobs and came within a rounding error of the same OOM
    ceiling the unsharded run was hitting), so a fixed company count per
    shard doesn't bound memory. Greedily bucketing by cumulative job count
    instead does."""
    companies = [_company(f"c{i}") for i in range(5)]
    # c0 alone is already at the job_target — must get its own shard rather
    # than being combined with anything else.
    job_counts = {"c0": 100, "c1": 10, "c2": 10, "c3": 10, "c4": 10}

    shards = main_module._shard(
        companies, shard_size=10, job_counts_by_company=job_counts, job_target=100
    )

    assert [c["name"] for c in shards[0]] == ["c0"]
    # c1-c4 (10 jobs each, 40 total) all fit under job_target=100 together.
    assert [c["name"] for c in shards[1]] == ["c1", "c2", "c3", "c4"]


def test_shard_job_count_bucketing_still_respects_shard_size_cap() -> None:
    """job_target alone would happily pack hundreds of tiny companies into
    one shard — shard_size remains an upper cap on company count per shard
    even when job counts are small, so a batch's own scrape-concurrency/
    failure-isolation properties (see test_shard_failure_does_not_lose_
    other_shards_results) don't degrade into one giant unscoped-feeling
    batch just because every company in it happens to be small."""
    companies = [_company(f"c{i}") for i in range(5)]
    job_counts = {f"c{i}": 1 for i in range(5)}  # trivially small, all well under any job_target

    shards = main_module._shard(
        companies, shard_size=2, job_counts_by_company=job_counts, job_target=1_000_000
    )

    assert [len(s) for s in shards] == [2, 2, 1]


def test_shard_falls_back_to_company_count_when_no_job_counts_available() -> None:
    """A brand-new pool (first-ever run, empty database) or a failed
    load_job_counts_by_company() call has no prior counts to bucket by —
    must fall back to the original fixed-company-count behavior rather
    than erroring or collapsing to one shard."""
    companies = [_company(f"c{i}") for i in range(5)]

    shards = main_module._shard(companies, shard_size=2, job_counts_by_company=None)

    assert [len(s) for s in shards] == [2, 2, 1]


def test_shard_size_run_uses_real_previous_job_counts(tmp_path: Path) -> None:
    """End-to-end: run() must actually load job counts from the database
    (not just accept them if handed) and use them to bucket the next run's
    shards — the real fix, not just _shard()'s unit-level logic."""
    companies = [_company(f"c{i}") for i in range(4)]
    # First run: c0 has a large pool (100 jobs), the rest are tiny (5 each) —
    # establishes "previous" counts for the second run to bucket by.
    db_url, deps = setup_run(
        tmp_path,
        companies=companies,
        jobs_by_company={
            "c0": [job("c0", f"c0:{i}") for i in range(100)],
            "c1": [job("c1", "c1:1") for _ in range(5)],
            "c2": [job("c2", "c2:1") for _ in range(5)],
            "c3": [job("c3", "c3:1") for _ in range(5)],
        },
    )
    assert main_module.run(database=db_url, deps=deps) == 0

    # Second run: same companies, shard_job_target set so c0's known 100-job
    # count alone should force it into its own shard, separate from c1-c3.
    write_calls = CountingWriteJobsStub(success=True)
    deps.write_jobs = write_calls
    result = main_module.run(database=db_url, deps=deps, shard_size=4, shard_job_target=50)

    assert result == 0
    # 4 companies, shard_size=4 would normally collapse to 1 shard — job
    # counts must have split it instead (c0 alone, c1-c3 together).
    assert write_calls.calls == 2


def test_scrape_companies_requeues_a_straggler_past_the_timeout() -> None:
    """A company still running past per_company_timeout_s must get a fresh
    attempt submitted behind it rather than blocking the rest of the batch —
    the fast retry's result is what gets counted."""
    call_count: dict[str, int] = {}
    unblock = threading.Event()

    def scrape_one(cfg: CompanyConfig) -> list[Job] | None:
        call_count[cfg["name"]] = call_count.get(cfg["name"], 0) + 1
        if cfg["name"] == "Acme" and call_count["Acme"] == 1:
            # First attempt stalls until the test explicitly releases it —
            # simulates a genuinely hung request.
            unblock.wait(timeout=5)
            return [job("Acme", "acme:stale")]
        if cfg["name"] == "Acme":
            return [job("Acme", "acme:fresh")]
        return [job(cfg["name"], f"{cfg['name'].lower()}:1")]

    completed, failed, results, interrupted = main_module._scrape_companies(
        [_company("Acme"), _company("Beta")],
        scrape_one,
        workers=4,
        per_company_timeout_s=0.2,
    )
    unblock.set()  # let the abandoned first attempt finish so the thread pool can join

    assert interrupted is False
    assert completed == {"Acme", "Beta"}
    assert failed == set()  # the requeued attempt succeeded, so Acme isn't a failure
    ids = {j.id for r in results if r is not None for j in r}
    # The fresh requeued attempt's result counts, not the stale original's.
    assert "acme:fresh" in ids
    assert "acme:stale" not in ids
    assert "beta:1" in ids
    assert call_count["Acme"] == 2


def test_scrape_companies_gives_up_after_max_requeue_attempts() -> None:
    """A company that stalls past the timeout on every attempt must
    eventually be counted as failed (None) instead of requeued forever."""

    def always_stalls(cfg: CompanyConfig) -> list[Job] | None:
        time.sleep(2)
        return [job(cfg["name"], "should-not-count")]

    completed, failed, results, interrupted = main_module._scrape_companies(
        [_company("Acme")],
        always_stalls,
        workers=4,
        per_company_timeout_s=0.1,
    )

    assert interrupted is False
    assert completed == {"Acme"}
    assert failed == {"Acme"}
    assert results == [None]
    time.sleep(2.5)  # let the abandoned background attempts actually finish


def test_scrape_companies_returns_promptly_despite_a_long_abandoned_straggler() -> None:
    """Regression test for a real hang found live on prod: once a company
    is abandoned (past MAX_REQUEUE_ATTEMPTS), _scrape_companies' own loop
    must return as soon as every OTHER company is done — it must not keep
    waiting on the abandoned straggler just because concurrent.futures.wait()
    keeps reporting it as "not done" for as long as its thread keeps
    running. The bug: wait()'s not_done return value was being assigned
    straight back to the loop's own `pending` set, which had no notion of
    "abandoned" — so a still-running abandoned future kept getting handed
    back into `pending` forever, and `while pending:` never became false.
    Confirmed live: a 36-company trial with two large, slow companies hung
    for 10+ minutes after every company had actually finished scraping,
    because two abandoned attempts were still slowly running in the
    background — this test reproduces that shape with a bounded timeout so
    a regression here fails fast instead of hanging the test suite."""
    STRAGGLER_DURATION_S = 3.0  # much longer than per_company_timeout_s below
    unblock = threading.Event()

    def scrape_one(cfg: CompanyConfig) -> list[Job] | None:
        if cfg["name"] == "SlowCo":
            # Simulates a real hung request: keeps "running" well past every
            # requeue attempt's own timeout, exactly like the abandoned
            # Workday/OracleCloud tenants seen live on prod.
            unblock.wait(timeout=STRAGGLER_DURATION_S)
            return [job("SlowCo", "slowco:stale")]
        return [job(cfg["name"], f"{cfg['name'].lower()}:1")]

    start = time.monotonic()
    completed, failed, results, interrupted = main_module._scrape_companies(
        [_company("SlowCo"), _company("FastCo1"), _company("FastCo2")],
        scrape_one,
        workers=4,
        per_company_timeout_s=0.1,
    )
    elapsed = time.monotonic() - start
    unblock.set()  # let the abandoned straggler's thread finish so the test can exit cleanly

    # The whole point: this must return once SlowCo has been abandoned
    # MAX_REQUEUE_ATTEMPTS times and the two fast companies are done —
    # NOT wait out the straggler's full multi-second duration.
    assert elapsed < STRAGGLER_DURATION_S / 2
    assert interrupted is False
    assert completed == {"SlowCo", "FastCo1", "FastCo2"}
    assert failed == {"SlowCo"}
    ids = {j.id for r in results if r is not None for j in r}
    assert ids == {"fastco1:1", "fastco2:1"}  # SlowCo's late/stale result never counted
    time.sleep(STRAGGLER_DURATION_S)  # let the background thread actually finish


def test_scrape_companies_queue_wait_does_not_count_as_timeout() -> None:
    """Regression test for the real prod bug behind Anthropic/Nokia (and
    ~900 other companies) getting falsely requeued/abandoned on nearly
    every scheduled run: with far more companies than worker threads, a
    company queued behind the worker limit can sit waiting for a free slot
    longer than per_company_timeout_s before its own scrape ever starts.
    The timeout must be judged from when a company's scrape actually
    started running, not from when it was submitted/queued — otherwise
    every company queued past roughly `workers * (timeout / avg_scrape_time)`
    gets flagged as "still running" and requeued/abandoned purely from
    queue wait, even though its own scrape is instant once it gets a
    worker. Confirmed live: prod runs 1294 companies through 16 workers
    with a 120s timeout, and ~900 companies (mostly queued toward the back
    of config.json) hit this on nearly every one of 52 consecutive runs."""
    workers = 2
    # Comfortably more companies than workers so several are still queued
    # when the first two occupy every worker slot.
    companies = [_company(f"Co{i}") for i in range(10)]
    # Each company's own scrape is instant — only queue wait could trigger
    # the timeout here. Held artificially longer than the polling interval
    # so every queued company gets at least one chance to be (wrongly)
    # evaluated against the timeout before finishing.
    hold = threading.Event()

    def scrape_one(cfg: CompanyConfig) -> list[Job] | None:
        hold.wait(timeout=1.0)
        return [job(cfg["name"], f"{cfg['name'].lower()}:1")]

    def release_soon() -> None:
        time.sleep(0.3)
        hold.set()

    releaser = threading.Thread(target=release_soon)
    releaser.start()
    _completed, failed, results, interrupted = main_module._scrape_companies(
        companies,
        scrape_one,
        workers=workers,
        # Shorter than the time a fully-queued company waits for a worker
        # slot (there are 10 companies / 2 workers, each holding ~0.3-1s),
        # but this must never fire just from sitting in the queue.
        per_company_timeout_s=0.15,
    )
    releaser.join()

    assert interrupted is False
    assert failed == set()  # nobody's own scrape ever actually stalled
    ids = {j.id for r in results if r is not None for j in r}
    assert ids == {f"co{i}:1" for i in range(10)}


def test_scrape_companies_fast_company_unaffected_by_timeout() -> None:
    def fast(cfg: CompanyConfig) -> list[Job] | None:
        return [job(cfg["name"], f"{cfg['name'].lower()}:1")]

    completed, failed, results, interrupted = main_module._scrape_companies(
        [_company("Acme"), _company("Beta")],
        fast,
        workers=4,
        per_company_timeout_s=30,
    )

    assert interrupted is False
    assert completed == {"Acme", "Beta"}
    assert failed == set()
    ids = {j.id for r in results if r is not None for j in r}
    assert ids == {"acme:1", "beta:1"}


def test_scrape_companies_none_timeout_preserves_original_unbounded_wait() -> None:
    def fast(cfg: CompanyConfig) -> list[Job] | None:
        return [job(cfg["name"], f"{cfg['name'].lower()}:1")]

    completed, failed, results, interrupted = main_module._scrape_companies(
        [_company("Acme"), _company("Beta")],
        fast,
        workers=4,
        per_company_timeout_s=None,
    )

    assert interrupted is False
    assert completed == {"Acme", "Beta"}
    assert failed == set()
    ids = {j.id for r in results if r is not None for j in r}
    assert ids == {"acme:1", "beta:1"}


def test_full_run_with_default_timeout_completes_normally(tmp_path: Path) -> None:
    """The new default-on per_company_timeout_s must not interfere with a
    normal, fast run — end-to-end through run(), not just _scrape_companies."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    result = main_module.run(database=db_url, deps=deps)  # default per_company_timeout_s

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1"}


def test_company_stalling_past_every_requeue_keeps_its_previous_jobs(tmp_path: Path) -> None:
    """Regression test for the real prod bug: Anthropic (Greenhouse) and
    Nokia (Oracle Cloud) both routinely took long enough that every requeue
    attempt got abandoned past per_company_timeout_s, which used to make
    that company vanish from `current` for the run entirely — and since a
    non-interrupted run's full_current was just `current` with no
    carry-forward for a merely-failed (as opposed to not-yet-attempted)
    company, its previously-written rows got deleted by write_jobs' own
    scope_companies full-replace with nothing to replace them. Two
    consecutive runs like this hit jobs/jobscraper_pool.py's
    MISSED_SCRAPES_BEFORE_DELISTING=2 and delisted 655 real, still-live
    Anthropic postings; Nokia (added later) never accumulated a single
    successful write at all. A company that stalls out on every attempt
    must instead keep its previously-known jobs untouched, exactly like an
    interrupted run already does for companies it never got to."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "StallCo", "board": "stub"},
        ],
        jobs_by_company={
            "Acme": [job("Acme", "acme:1")],
            "StallCo": [job("StallCo", "stallco:1")],
        },
    )

    # Seed a full previous snapshot with both companies successfully scraped.
    assert main_module.run(database=db_url, deps=deps) == 0
    assert db_job_ids(db_url) == {"acme:1", "stallco:1"}

    # Now StallCo's board hangs past every requeue attempt on the next run —
    # exactly the shape seen live on prod — while Acme scrapes fine and even
    # has a genuinely new posting.
    class StallingScraper(BaseScraper):
        def fetch_jobs(self) -> list[Job]:
            if self.company["name"] == "StallCo":
                time.sleep(2)
                return [job("StallCo", "stallco:should-not-count")]
            return jobs_by_company_state[self.company["name"]]

    deps.scrapers = {"stub": StallingScraper}
    jobs_by_company_state["Acme"] = [job("Acme", "acme:2")]

    result = main_module.run(database=db_url, deps=deps, per_company_timeout_s=0.1)

    assert result == 0
    # StallCo's old job must survive untouched — not deleted, not replaced
    # by the late "should-not-count" result. Acme's fresh listing still
    # takes effect normally.
    assert db_job_ids(db_url) == {"acme:2", "stallco:1"}
    time.sleep(2.5)  # let the abandoned background attempt actually finish


def test_main_calls_os_exit_not_sys_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() must call os._exit(), not sys.exit() — a requeued/abandoned
    company (see _scrape_companies) can leave a non-daemon worker thread
    still retrying a dead connection, and stdlib ThreadPoolExecutor threads
    are never daemon threads, so a plain sys.exit()-triggered interpreter
    shutdown would block joining it (confirmed live: 2.5+ minutes of pure
    waste after a run's real work was already done). This test locks in
    that main() takes the hard-exit path rather than silently regressing
    back to sys.exit() in some future refactor."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.setattr(main_module, "RunDeps", lambda: deps)
    monkeypatch.setattr("sys.argv", ["scraper.main", "--database", db_url])

    exit_calls: list[int] = []

    def fake_os_exit(code: int) -> None:
        exit_calls.append(code)
        raise SystemExit(code)  # stand in for the real hard exit in this test process

    monkeypatch.setattr(main_module.os, "_exit", fake_os_exit)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exit_calls == [0]
    assert exc_info.value.code == 0
    assert db_job_ids(db_url) == {"acme:1"}
