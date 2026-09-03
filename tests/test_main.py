import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

import scraper.main as main_module
from scraper.boards.base import BaseScraper
from scraper.config_types import CompanyConfig
from scraper.db import jobs_table
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


class CountingStub:
    """A summarize_role-shaped stub that tracks how many times it was called."""

    def __init__(self, return_value: str = "") -> None:
        self.return_value = return_value
        self.calls = 0

    def __call__(self, *args: object) -> str:
        self.calls += 1
        return self.return_value


class CountingWriteJobsStub:
    """A write_jobs-shaped stub that tracks how many times it was called."""

    def __init__(self, success: bool) -> None:
        self.success = success
        self.calls = 0

    def __call__(self, database: str, jobs: list[Job], new_ids: set[str]) -> bool:
        self.calls += 1
        return self.success


class FlakyWriteJobsStub:
    """A write_jobs-shaped stub that fails its first `fail_times` calls, then
    succeeds — simulates a transient SQLITE_BUSY that clears up on retry."""

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, database: str, jobs: list[Job], new_ids: set[str]) -> bool:
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
        summarize_role=lambda title, company, description: "",
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
    summarize_calls = CountingStub()
    deps.summarize_role = summarize_calls

    result = main_module.run(deps=deps)  # no database=, no limit=

    # --database is the only sink now — without it (and without --limit,
    # which exempts the smoke-test path) there'd be nowhere to write the
    # results, so this must fail fast rather than silently scrape for nothing.
    assert result == 1
    assert summarize_calls.calls == 0


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

    assert write_calls.calls == 3
    assert result == 1


def test_write_failure_retries_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient write failure (e.g. SQLITE_BUSY from a concurrent Node
    write against the shared data/app.db, see GitHub issue #38) should not
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
    summarize_calls = CountingStub()
    deps.summarize_role = summarize_calls
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
    assert summarize_calls.calls == 0  # skipped entirely once interrupted


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
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    summarize_calls = CountingStub()
    deps.summarize_role = summarize_calls

    result = main_module.run(llm_provider="ollama", database=db_url, deps=deps)

    assert result == 0
    assert os.environ["LLM_PROVIDER"] == "ollama"
    assert summarize_calls.calls == 1


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
    """Every board scraper builds a fresh Job() each run (role_summary=""
    by dataclass default), and the summarize step only runs for genuinely
    new jobs — without carrying the previous run's role_summary forward for
    already-known jobs, their real summary would be silently overwritten
    with "" on every subsequent run, even though summarize_role is
    correctly never re-called for them."""
    db_url, deps = setup_run(
        tmp_path,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    first_summarize_calls = CountingStub("Builds great things.")
    deps.summarize_role = first_summarize_calls

    assert main_module.run(database=db_url, deps=deps) == 0

    assert db_role_summary(db_url, "acme:1") == "Builds great things."
    assert first_summarize_calls.calls == 1

    # Second run: same job id, but a FRESH Job object (role_summary="" by
    # default) — exactly what every real board scraper produces, since none
    # of them read role_summary back from anywhere.
    jobs_by_company_state["Acme"] = [job("Acme", "acme:1")]
    second_summarize_calls = CountingStub()
    deps.summarize_role = second_summarize_calls

    assert main_module.run(database=db_url, deps=deps) == 0

    # Not re-requested (correct, unchanged behavior) — and critically, the
    # real summary from run 1 must survive, not get overwritten with "".
    assert second_summarize_calls.calls == 0
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
