import json
import os
from unittest.mock import patch

from sqlalchemy import create_engine, select

import scraper.main as main_module
from scraper.db import jobs_table
from scraper.models import Job


def write_config(path, companies):
    path.write_text(
        json.dumps({"companies": companies}),
        encoding="utf-8",
    )


class StubScraper:
    """Registered under a fake board name; returns whatever jobs are queued for it."""

    def __init__(self, company_cfg, settings=None, previous=None):
        self.company_cfg = company_cfg

    def fetch_jobs(self):
        return JOBS_BY_COMPANY[self.company_cfg["name"]]


JOBS_BY_COMPANY: dict[str, list[Job]] = {}


def job(company, jid, title="Senior Staff Manager Intern", posted_days=None):
    """Deliberately blacklist-shaped title — must survive since filtering is gone."""
    return Job(
        id=jid, company=company, title=title, location="Paris, France",
        locations=["Paris, France"], url="https://example.com",
        posted_on="Posted Today", source="stub", posted_days=posted_days,
    )


def setup_run(tmp_path, monkeypatch, companies, jobs_by_company):
    global JOBS_BY_COMPANY
    JOBS_BY_COMPANY = jobs_by_company
    config_path = tmp_path / "config.json"
    write_config(config_path, companies)
    monkeypatch.setattr(main_module, "CONFIG_PATH", config_path)
    monkeypatch.setitem(main_module.SCRAPERS, "stub", StubScraper)
    return f"sqlite:///{tmp_path / 'jobs.db'}"


def db_job_ids(db_url):
    engine = create_engine(db_url)
    with engine.connect() as conn:
        return {r.id for r in conn.execute(select(jobs_table))}


def db_role_summary(db_url, job_id):
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(select(jobs_table).where(jobs_table.c.id == job_id)).fetchone()
        return row.role_summary if row else None


def test_full_run_stores_every_job_unfiltered(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(database=db_url)

    assert result == 0
    # A blacklisted-looking, all-foreign-location job survives — no storage filter.
    assert db_job_ids(db_url) == {"acme:1"}


def test_full_run_without_database_or_limit_errors(tmp_path, monkeypatch):
    setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value="") as mock_summarize:
        result = main_module.run()  # no database=, no limit=

    # --database is the only sink now — without it (and without --limit,
    # which exempts the smoke-test path) there'd be nowhere to write the
    # results, so this must fail fast rather than silently scrape for nothing.
    assert result == 1
    mock_summarize.assert_not_called()


def test_company_scoped_run_merges_into_existing_snapshot(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={"Acme": [job("Acme", "acme:1")], "Beta": [job("Beta", "beta:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        # Seed a full previous state (in --database, the --company merge's
        # source) with both companies.
        assert main_module.run(database=db_url) == 0

        # Now Acme has a fresh listing; Beta isn't re-scraped this run.
        JOBS_BY_COMPANY["Acme"] = [job("Acme", "acme:2")]
        result = main_module.run(company="Acme", database=db_url)

    assert result == 0
    # Beta's job is untouched; Acme's old job is gone, replaced by the fresh one.
    assert db_job_ids(db_url) == {"beta:1", "acme:2"}


def test_company_scoped_run_requires_database(tmp_path, monkeypatch):
    setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(company="Acme")  # no database=

    assert result == 1


def test_company_scoped_run_with_limit_does_not_require_database(tmp_path, monkeypatch):
    setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        # --limit is a smoke test — skips the --database requirement too.
        result = main_module.run(company="Acme", limit=1)

    assert result == 0


def test_unknown_company_name_errors(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": []},
    )

    assert main_module.run(company="Nonexistent", database=db_url) == 1


def test_database_flag_mirrors_snapshot_into_sql_db(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(database=db_url)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1"}


def test_database_write_skipped_when_limit_set(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    db_path = tmp_path / "jobs.db"

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(limit=1, database=db_url)

    assert result == 0
    assert not db_path.exists()


def test_write_failure_fails_the_run(tmp_path, monkeypatch):
    """write_jobs() now reports success/failure explicitly instead of
    swallowing every exception — confirmed in practice 2026-08-14 that a
    silently-swallowed write failure let --jobscraper-pipeline see exit 0
    and proceed against unchanged data. run() must propagate a real failure
    into a non-zero exit code."""
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with (
        patch.object(main_module, "summarize_role", return_value=""),
        patch.object(main_module, "write_jobs", return_value=False) as mock_write,
    ):
        result = main_module.run(database=db_url)

    mock_write.assert_called_once()
    assert result == 1


def test_interrupted_run_saves_completed_companies_and_keeps_others_unchanged(
    tmp_path, monkeypatch
):
    """Ctrl-C partway through a full run must not lose whatever already
    finished, and must not silently delete companies that hadn't been
    reached yet from the pool. Simulates: Acme finishes normally, Beta's
    scrape raises KeyboardInterrupt (the point where a real Ctrl-C would
    land mid-request) — Zeta, already in a previous snapshot, was never
    even reached this run.
    """
    db_url = setup_run(
        tmp_path, monkeypatch,
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
    with patch.object(main_module, "summarize_role", return_value=""):
        main_module.run(database=db_url)

    class InterruptingScraper(StubScraper):
        def fetch_jobs(self):
            if self.company_cfg["name"] == "Beta":
                raise KeyboardInterrupt
            return super().fetch_jobs()

    monkeypatch.setitem(main_module.SCRAPERS, "stub", InterruptingScraper)
    # concurrency=1 makes ordering deterministic: Acme completes, then
    # Beta's KeyboardInterrupt fires before Zeta is ever submitted.
    with patch.object(main_module, "summarize_role", return_value="") as mock_summarize:
        result = main_module.run(database=db_url, concurrency=1)

    assert result == 130  # 128+SIGINT — distinguishes interrupted-but-saved from clean/failed
    ids = db_job_ids(db_url)
    assert "acme:1" in ids  # completed before the interrupt — saved
    assert "zeta:1" in ids  # never reached this run — carried forward from previous snapshot
    # Beta's own scrape raised before producing a job, so nothing new to
    # carry for it either way — this assertion documents that, not a
    # requirement that beta:1 must be absent.
    mock_summarize.assert_not_called()  # skipped entirely once interrupted


def test_concurrency_flag_is_accepted_and_threaded_through(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[
            {"name": "Acme", "board": "stub"},
            {"name": "Beta", "board": "stub"},
        ],
        jobs_by_company={"Acme": [job("Acme", "acme:1")], "Beta": [job("Beta", "beta:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(concurrency=1, database=db_url)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1", "beta:1"}


def test_concurrency_flag_defaults_when_omitted(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(database=db_url)

    assert result == 0
    assert db_job_ids(db_url) == {"acme:1"}


def test_llm_provider_flag_sets_env_for_summarize(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with patch.object(main_module, "summarize_role", return_value="") as mock_summarize:
        result = main_module.run(llm_provider="ollama", database=db_url)

    assert result == 0
    assert os.environ["LLM_PROVIDER"] == "ollama"
    mock_summarize.assert_called_once()


def test_llm_provider_omitted_leaves_env_untouched(tmp_path, monkeypatch):
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with patch.object(main_module, "summarize_role", return_value=""):
        result = main_module.run(database=db_url)

    assert result == 0
    assert "LLM_PROVIDER" not in os.environ


def test_role_summary_carried_over_for_already_known_job(tmp_path, monkeypatch):
    """Every board scraper builds a fresh Job() each run (role_summary=""
    by dataclass default), and the summarize step only runs for genuinely
    new jobs — without carrying the previous run's role_summary forward for
    already-known jobs, their real summary would be silently overwritten
    with "" on every subsequent run, even though summarize_role is
    correctly never re-called for them."""
    db_url = setup_run(
        tmp_path, monkeypatch,
        companies=[{"name": "Acme", "board": "stub"}],
        jobs_by_company={"Acme": [job("Acme", "acme:1")]},
    )

    with patch.object(main_module, "summarize_role", return_value="Builds great things.") as mock_summarize:
        assert main_module.run(database=db_url) == 0

    assert db_role_summary(db_url, "acme:1") == "Builds great things."
    mock_summarize.assert_called_once()

    # Second run: same job id, but a FRESH Job object (role_summary="" by
    # default) — exactly what every real board scraper produces, since none
    # of them read role_summary back from anywhere.
    JOBS_BY_COMPANY["Acme"] = [job("Acme", "acme:1")]

    with patch.object(main_module, "summarize_role", return_value="") as mock_summarize:
        assert main_module.run(database=db_url) == 0

    # Not re-requested (correct, unchanged behavior) — and critically, the
    # real summary from run 1 must survive, not get overwritten with "".
    mock_summarize.assert_not_called()
    assert db_role_summary(db_url, "acme:1") == "Builds great things."
