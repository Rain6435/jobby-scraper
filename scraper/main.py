"""Orchestrator: scrape companies, diff against prior state, write to --database.

This is an unfiltered job pool — every currently-listed posting from every
configured company is stored, with no keyword/title/location/age curation.
Consumer apps are expected to filter for their own use case downstream. A
job leaves the pool once a fresh scrape's listing no longer includes it
(closed/filled/expired) — --database is a full-replace write of exactly what
this run scraped, not an accumulating log.

--database is required for a full run: it's both the only state sink and
the sole source of "previous run" state for new-job detection, first_seen
carryover, and each board's detail-fetch cache (BaseScraper._cached_detail).
docs/jobs.json is no longer written — this pipeline no longer has a
GitHub Pages dashboard consumer, so that write (and the read-back that used
to matter before --database existed) was pure wasted I/O.

Usage:
    python -m scraper.main --database "sqlite:///jobs.db"  # full run
    python -m scraper.main --company "Acme" --database "sqlite:///jobs.db"
                                                      # on-demand refresh: scrape + merge
                                                      # just this company into the previous
                                                      # run's full job set (--database required)
    python -m scraper.main --company "Acme" --limit 1  # smoke test, no write, no --database
                                                      # requirement either
    python -m scraper.main --database "sqlite:///jobs.db" --verbose  # per-request/job detail
    python -m scraper.main --database "postgresql+psycopg2://user:pass@host/db"
                                                      # any SQLAlchemy URL
    python -m scraper.main --database "sqlite:///jobs.db" --concurrency 16
                                                      # scrape more companies in parallel
                                                      # (default 16; board scrapers retry
                                                      # transient failures with backoff)

Env (also loadable from a .env file in the repo root — see .env.example):
    ANTHROPIC_API_KEY    optional — enables AI role summaries for new jobs.
                          Pipeline runs fully without it (summaries just
                          stay blank). ANTHROPIC_AUTH_TOKEN also works.
    OLLAMA_API_KEY        optional — fallback for AI summaries when Anthropic
                          is unconfigured or its call fails (see --llm-provider
                          to pin to just one instead of falling back).
    LOG_LEVEL            DEBUG/INFO/WARNING/ERROR (default INFO); same effect as --verbose
                          when set to DEBUG
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from scraper.boards import SCRAPERS
from scraper.db import load_previous, write_jobs
from scraper.models import Job
from scraper.storage import diff
from scraper.summarize import summarize_role

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONCURRENCY = 16

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scraper")


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def _configure_log_level(verbose: bool) -> None:
    """--verbose or LOG_LEVEL=DEBUG bumps every scraper.* logger to DEBUG."""
    level_name = "DEBUG" if verbose else os.environ.get("LOG_LEVEL", "INFO").upper()
    level = _LEVELS.get(level_name, logging.INFO)
    logging.getLogger("scraper").setLevel(level)


def run(
    company: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
    database: str | None = None,
    concurrency: int | None = None,
    no_detail_cache: bool = False,
    llm_provider: str | None = None,
) -> int:
    _configure_log_level(verbose)
    if llm_provider:
        # scraper/summarize.py reads this to pin to one provider instead of
        # its default try-Anthropic-then-Ollama fallback.
        os.environ["LLM_PROVIDER"] = llm_provider
    run_started = time.monotonic()
    log.debug("Config path: %s", CONFIG_PATH)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # board-agnostic options passed to every scraper's __init__ — currently
    # empty (max_age_days was the only one, now removed: every board fetches
    # its full current listing every run, no age-based filtering).
    settings: dict = {}
    log.debug("Loaded config: %d companies", len(config["companies"]))

    # --database is the only sink now (docs/jobs.json is no longer written),
    # so without it a real run would do all the scrape work and then persist
    # nothing — a silent no-op. --limit is exempt: it's a smoke test that
    # never touches the database in either direction by design.
    if limit is None and not database:
        log.error(
            "--database is required (it's the only place this run's results "
            "are written — see scraper/db.py). Pass --limit instead for a "
            "smoke test that doesn't need it."
        )
        return 1

    companies = config["companies"]
    if company is not None:
        companies = [c for c in companies if c["name"] == company]
        if not companies:
            log.error("No configured company named %r", company)
            return 1

    log.info("Scraping %d compan%s...", len(companies), "y" if len(companies) == 1 else "ies")

    # previous drives new-job detection, first_seen carryover, and each
    # board's detail-fetch cache (BaseScraper._cached_detail) — read from
    # --database (whatever write_jobs() last wrote there). --limit is a smoke
    # test that must never touch the real database in either direction (same
    # contract as write_jobs() below being skipped for --limit) — even a
    # read would create the file via metadata.create_all(), so it's skipped
    # here too.
    if database and limit is None:
        previous = load_previous(database)
    else:
        log.debug("--limit set — skipping --database read for this smoke-test run")
        previous = {}
    log.debug("Previous state: %d known jobs", len(previous))

    # `previous` drives three separate things: the boards' detail-fetch cache
    # (BaseScraper._cached_detail), first_seen carryover, and diff()'s new-job
    # detection. --no-detail-cache withholds it from the FIRST of those only.
    #
    # The four detail-fetch boards (workday/rippling/bamboohr/smartrecruiters)
    # skip a posting's detail GET — and therefore reuse its cached description —
    # whenever its id is in `previous`. That's the right default, but it also
    # means a description captured under an older, smaller truncation cap is
    # carried forward forever: re-scraping alone never repairs it. Passing an
    # empty dict to the scrapers forces every posting's detail to be re-fetched
    # once, which is the whole point of a backfill run.
    #
    # Emptying `previous` outright instead would be a bug with two expensive
    # consequences: every job's first_seen would reset (and posted_date with
    # it, since db.py derives it from first_seen), and diff() would report the
    # entire pool as new — firing an AI role summary for every single job.
    scraper_previous: dict[str, Job] = {} if no_detail_cache else previous
    if no_detail_cache:
        log.info(
            "--no-detail-cache: re-fetching every posting's detail page "
            "(first_seen/diff still use the %d known jobs)",
            len(previous),
        )

    def scrape_one(company_cfg: dict) -> list[Job] | None:
        """Scrape a single company; None signals failure (logged, never fatal)."""
        board = company_cfg["board"]
        scraper_cls = SCRAPERS.get(board)
        if scraper_cls is None:
            log.error("Unknown board %r for %s — skipping", board, company_cfg["name"])
            return None
        started = time.monotonic()
        log.debug("%s: scraping via %s board", company_cfg["name"], board)
        try:
            jobs = scraper_cls(company_cfg, settings, previous=scraper_previous).fetch_jobs()
            elapsed = time.monotonic() - started
            log.info("%s: %d jobs (%.1fs)", company_cfg["name"], len(jobs), elapsed)
            return jobs
        except Exception:
            log.exception("Scrape failed for %s — continuing", company_cfg["name"])
            return None

    # Companies are independent and network-bound — scrape them in parallel.
    # Each scraper builds its own requests.Session, so threads don't share state.
    # Most companies hit distinct hosts (their own Workday tenant, Greenhouse
    # token, etc.), so raising this mostly increases cross-host throughput
    # rather than the request rate against any single host; each session also
    # retries transient failures (429/5xx) with backoff (scraper.boards.base
    # .make_session), so higher concurrency doesn't just produce more 429s.
    #
    # submit()+as_completed() rather than pool.map(): map() only yields once
    # EVERY task is done (or raises), so a Ctrl-C partway through a ~166-
    # company run had nothing to show for whatever had already finished —
    # results were held inside the executor, inaccessible once the process
    # unwound. Tracking futures individually means a KeyboardInterrupt here
    # can still fall through to the partial-write path below with whatever
    # companies did complete, instead of losing the entire run's work.
    workers = concurrency if concurrency is not None else DEFAULT_CONCURRENCY
    scrape_started = time.monotonic()
    completed_names: set[str] = set()
    results: list[list[Job] | None] = []
    interrupted = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scrape_one, c): c for c in companies}
        try:
            for future in as_completed(futures):
                completed_names.add(futures[future]["name"])
                results.append(future.result())
        except KeyboardInterrupt:
            interrupted = True
            log.warning(
                "Interrupted — %d/%d companies had already finished scraping; "
                "saving their results instead of discarding the run",
                len(results), len(companies),
            )
            for f in futures:
                f.cancel()
    log.debug("Scrape phase took %.1fs total", time.monotonic() - scrape_started)

    failures = sum(1 for r in results if r is None)
    current: list[Job] = [job for r in results if r is not None for job in r]
    log.info(
        "Scraped %d jobs across %d companies (%d scrape failures)",
        len(current), len(results), failures,
    )

    # No age filtering — every currently-listed posting is stored, every
    # run. A job leaves the pool once a fresh scrape's listing no longer
    # includes it (closed/filled/expired), not because it crossed a fixed
    # day count: --database is a full-replace write of exactly
    # `full_current` below.
    if limit is not None:
        log.info("--limit %d applied: capping %d jobs down to %d", limit, len(current), min(limit, len(current)))
        current = current[:limit]

    if not current and failures:
        log.error("All scrapers failed; keeping previous snapshot untouched")
        return 1

    # Denormalize each company's AI blurb (generated once, cached in
    # config.json by scraper/backfill_blurbs.py) onto every one of its jobs —
    # consumers only ever read --database, never config.json, so this is the
    # only way the blurb reaches them (see db.py's companies_table.blurb,
    # written once per company rather than duplicated per job there).
    blurbs = {c["name"]: c.get("blurb", "") for c in config["companies"]}
    for job in current:
        job.company_blurb = blurbs.get(job.company, "")

    # Carry over first_seen and role_summary for jobs we already knew about.
    # Every board scraper builds a fresh Job() each run (role_summary="" by
    # dataclass default), and the summarize step below only runs for
    # new_jobs — so without this, every already-known job's previously
    # generated summary would be silently overwritten with "" on the next
    # write, even though the summarize step correctly never re-requests it.
    # Same failure mode Job.posted_date already documents and guards against.
    for job in current:
        if job.id in previous:
            job.first_seen = previous[job.id].first_seen
            job.role_summary = previous[job.id].role_summary

    # When scoped to one company (on-demand refresh), the full snapshot to
    # diff/save is: everyone else's jobs from the previous snapshot, unchanged,
    # plus this company's freshly scraped jobs. An interrupted full run uses
    # the same shape, just scoped to whichever companies didn't finish
    # in time — carrying their previous jobs forward rather than dropping
    # them, so Ctrl-C partway through a run degrades to "save what's done,
    # leave the rest as it was" instead of losing the whole run's progress
    # (or, if we instead wrote only `current`, silently deleting every
    # not-yet-scraped company from the pool on the next write).
    if company is not None:
        full_current = [j for j in previous.values() if j.company != company] + current
    elif interrupted:
        full_current = [j for j in previous.values() if j.company not in completed_names] + current
    else:
        full_current = current

    new_jobs = diff(previous, full_current)
    log.info("%d new jobs", len(new_jobs))
    for j in new_jobs:
        log.debug("New job: %s — %s @ %s", j.id, j.title, j.company)

    # AI role summaries: for every new job. Best-effort — summarize_role()
    # never raises, so no failure here can abort the run; ANTHROPIC_API_KEY
    # absent just means every summary stays "". Skipped entirely when
    # interrupted — the operator asked this run to stop, and a summary call
    # per new job is exactly the kind of extra network round-trip that
    # shouldn't run after a Ctrl-C, on top of delaying the save it triggered.
    summarized = 0
    if interrupted:
        log.info("Interrupted — skipping AI role summaries for %d new jobs", len(new_jobs))
    else:
        for job in new_jobs:
            log.debug("Requesting AI role summary for %s @ %s", job.title, job.company)
            job.role_summary = summarize_role(job.title, job.company, job.description)
            if job.role_summary:
                summarized += 1
                log.info("Role summary for %s @ %s: %s", job.title, job.company, job.role_summary)
        if new_jobs:
            log.info("AI role summaries: %d of %d succeeded", summarized, len(new_jobs))

    if limit is not None:
        # --limit truncates the scraped list arbitrarily — writing that as
        # the full snapshot would discard jobs it never even considered, and
        # this is a smoke test, not a real run. Skip the write.
        log.info("--limit set — skipping database write (%d jobs)", len(full_current))
        log.info("Run finished in %.1fs", time.monotonic() - run_started)
        return 0

    # --database is the only sink now (docs/jobs.json is gone), so a failed
    # write here means this run's results are lost — write_jobs() reports
    # success/failure explicitly rather than swallowing it, and this run
    # must fail loudly (non-zero exit) when it does, or a caller like
    # main.py's --jobscraper-pipeline sees exit 0 and proceeds to
    # ingest/parse against unchanged data (confirmed happening in practice
    # 2026-08-14 before this check existed).
    assert database is not None  # guaranteed by the --database-required check above
    if not write_jobs(database, full_current, {j.id for j in new_jobs}):
        log.error("Database write failed — run's results were NOT persisted")
        return 1

    if interrupted:
        log.warning(
            "Run interrupted after %.1fs — saved %d/%d companies scraped before "
            "Ctrl-C, remaining companies carried forward unchanged from the "
            "previous snapshot",
            time.monotonic() - run_started, len(completed_names), len(companies),
        )
        # 130 = 128+SIGINT, the conventional shell exit code for
        # Ctrl-C — distinguishes "interrupted, partial save" from both a
        # clean run (0) and a hard failure (1) for any caller checking the
        # exit code (e.g. main.py's --jobscraper-pipeline).
        return 130

    log.info("Run finished in %.1fs", time.monotonic() - run_started)
    return 0


def main() -> None:
    load_dotenv()  # local .env is optional; GitHub Actions injects real secrets instead
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--company",
        help="only scrape this one company (must match a 'name' in config.json) and "
        "merge its fresh jobs into the previous run's full job set — an "
        "on-demand refresh of just that company. Requires --database (that's "
        "both the merge source — everyone else's prior jobs — and the only "
        "place this run's results get written). Combine with --limit for a "
        "smoke test that skips the --database requirement, the read, and "
        "the write.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="cap the scraped job list to the first N jobs before diff/summarize; "
        "implies skipping the database write (smoke test)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG-level logging: per-request/per-job detail, stage timing. "
        "Same effect as LOG_LEVEL=DEBUG",
    )
    parser.add_argument(
        "--database",
        help="where this run's results are written, as a SQLAlchemy connection "
        "URL, e.g. 'postgresql+psycopg2://user:pass@host/db' or "
        "'sqlite:///jobs.db'. Required unless --limit is set (a smoke test "
        "that never touches the database). Also the source of 'previous run' "
        "state for new-job detection, first_seen carryover, and the "
        "detail-fetch cache. Requires the target dialect's driver package "
        "installed (SQLite needs none). Best-effort — a failed write is "
        "logged, never fatal to the run, but since this is now the only "
        "sink, a failed write does mean this run's results are lost.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help=f"number of companies to scrape in parallel (default {DEFAULT_CONCURRENCY}). "
        "Each board scraper retries transient failures (429/5xx/connection "
        "errors) with backoff, so raising this is safe even under rate "
        "limiting — most companies hit distinct hosts, so it mainly increases "
        "cross-host throughput rather than the request rate against any one host.",
    )
    parser.add_argument(
        "--no-detail-cache",
        action="store_true",
        help="force every posting's detail page to be re-fetched instead of "
        "reusing the previous run's cached description. One-time backfill "
        "tool: descriptions scraped under an older truncation cap are "
        "otherwise carried forward forever, since the detail-fetch boards "
        "(workday/rippling/bamboohr/smartrecruiters) skip the detail GET for "
        "any job they've already seen. Slow — roughly one extra HTTP request "
        "per known job on those boards — so this is not for routine runs. "
        "first_seen, posted_date, and new-job detection are unaffected.",
    )
    parser.add_argument(
        "--llm-provider",
        choices=["anthropic", "ollama"],
        default=None,
        help="pin AI role summaries/company blurbs (scraper/summarize.py) to "
        "just this one provider — the other is never attempted, so a "
        "failure returns '' instead of silently falling back. Default: try "
        "Anthropic first, fall back to Ollama if it's unconfigured or fails.",
    )
    args = parser.parse_args()
    sys.exit(run(
        company=args.company,
        limit=args.limit,
        verbose=args.verbose,
        database=args.database,
        concurrency=args.concurrency,
        no_detail_cache=args.no_detail_cache,
        llm_provider=args.llm_provider,
    ))


if __name__ == "__main__":
    main()
