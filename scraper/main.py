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
    python -m scraper.main --database "sqlite:///jobs.db" --shard-size 100
                                                      # split into 100-company batches,
                                                      # each scraped/diffed/written on its
                                                      # own (bounded memory, isolated failures)
    python -m scraper.main --database "sqlite:///jobs.db" --per-company-timeout 60
                                                      # requeue any company still scraping
                                                      # after 60s instead of blocking on it
                                                      # (on by default at 120s)

Env (also loadable from a .env file in the repo root — see .env.example):
    ANTHROPIC_API_KEY    optional — used only by the separate `python -m
                          scraper.backfill_blurbs` company-blurb tool, not by
                          this scrape run. role_summary is no longer
                          generated here at all — see "AI Summaries and
                          Company Blurbs" in CLAUDE.md. ANTHROPIC_AUTH_TOKEN
                          also works for backfill_blurbs.
    OLLAMA_API_KEY        optional — fallback for backfill_blurbs when
                          Anthropic is unconfigured or its call fails (see
                          --llm-provider to pin to just one instead of
                          falling back).
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
from collections.abc import Callable
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from scraper.boards import SCRAPERS
from scraper.boards.base import BaseScraper
from scraper.config_types import CompanyConfig, ConfigFile
from scraper.db import checkpoint_wal, load_previous, update_role_summary, write_jobs
from scraper.models import Job
from scraper.storage import diff

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DEFAULT_CONCURRENCY = 16

# How long a single company's scrape may run before it's considered a
# straggler. Not a hard kill: requests/urllib3 calls in a worker thread
# can't be forcibly interrupted from outside, so a stalled scrape_one()
# keeps occupying its worker slot regardless — this timeout only stops it
# from blocking the REST of the batch. See _scrape_companies' docstring.
# IBM's own ~2000-job scrape took ~22s in a live smoke test; most boards
# are far smaller, so 120s gives real slow-but-fine companies (large
# Workday tenants doing a detail GET per posting) headroom without letting
# one genuinely stuck host hold up an entire shard.
DEFAULT_PER_COMPANY_TIMEOUT_S = 120

# A company that stalls twice in a row is treated as failed rather than
# requeued a third time — an unbounded requeue loop against a company
# that's simply unreachable this run would otherwise tie up a worker slot
# with a fresh doomed attempt forever, one requeue after another.
MAX_REQUEUE_ATTEMPTS = 2

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scraper")


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


@dataclass
class RunDeps:
    """Injectable seam for run()'s external effects — real implementations
    by default; tests substitute stubs here instead of monkeypatching this
    module's globals."""

    config_path: Path = CONFIG_PATH
    scrapers: dict[str, type[BaseScraper]] = field(default_factory=lambda: dict(SCRAPERS))
    write_jobs: Callable[..., bool] = write_jobs
    load_previous: Callable[..., dict[str, Job]] = load_previous
    update_role_summary: Callable[[str, str, str], bool] = update_role_summary
    checkpoint_wal: Callable[[str], None] = checkpoint_wal


def _configure_log_level(verbose: bool) -> None:
    """--verbose or LOG_LEVEL=DEBUG bumps every scraper.* logger to DEBUG."""
    level_name = "DEBUG" if verbose else os.environ.get("LOG_LEVEL", "INFO").upper()
    level = _LEVELS.get(level_name, logging.INFO)
    logging.getLogger("scraper").setLevel(level)


def _scrape_companies(
    companies: list[CompanyConfig],
    scrape_one: Callable[[CompanyConfig], list[Job] | None],
    *,
    workers: int,
    per_company_timeout_s: float | None,
) -> tuple[set[str], list[list[Job] | None], bool]:
    """Run scrape_one for every company in a bounded thread pool, requeuing
    (not killing) any company that's still running past per_company_timeout_s.

    Python can't forcibly interrupt a worker thread blocked inside a
    requests/urllib3 call — there is no safe cross-thread cancel for a
    stalled scrape_one(). So a straggler is never killed: past the timeout,
    a FRESH attempt for that same company is submitted alongside the
    original (effectively re-queued behind whatever else is already
    pending), and the original's eventual result — whenever it finally
    returns — is discarded rather than double-counted. This costs one
    worker slot for as long as the abandoned original keeps running, but it
    means everyone else keeps moving instead of the whole batch blocking on
    one slow host. A company that stalls MAX_REQUEUE_ATTEMPTS times in a
    row is left to run to completion in the background and simply counted
    as a failure for this batch, rather than requeued forever.

    per_company_timeout_s=None disables this entirely — every future is
    waited on with no timeout, identical to the original as_completed()
    loop this replaces.

    Returns (completed_names, results, interrupted) — completed_names is
    every company name that got at least one non-abandoned attempt
    scheduled (used for the interrupted-run "carry forward unscraped
    companies" path), results is one list[Job]|None per company actually
    counted (excludes abandoned stragglers and any of their duplicate
    late-arriving results), interrupted mirrors the original Ctrl-C
    contract.
    """
    if per_company_timeout_s is None:
        # Original, unbounded behavior — no polling loop needed.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(scrape_one, c): c for c in companies}
            completed_names: set[str] = set()
            results: list[list[Job] | None] = []
            try:
                for future in wait(futures, return_when=ALL_COMPLETED).done:
                    completed_names.add(futures[future]["name"])
                    results.append(future.result())
                return completed_names, results, False
            except KeyboardInterrupt:
                log.warning(
                    "Interrupted — %d/%d companies had already finished scraping; "
                    "saving their results instead of discarding the run",
                    len(results),
                    len(companies),
                )
                for f in futures:
                    f.cancel()
                return completed_names, results, True

    completed_names = set()
    results = []
    # One entry per LIVE attempt (original or requeued). abandoned tracks
    # attempts whose result must be discarded when they eventually arrive —
    # a company's own worst case is bounded by MAX_REQUEUE_ATTEMPTS, not by
    # how long any individual abandoned attempt happens to keep running.
    abandoned: set[Future[list[Job] | None]] = set()
    poll_interval = min(per_company_timeout_s, 5.0)

    # Deliberately not a `with ThreadPoolExecutor(...) as pool:` block: that
    # context manager's __exit__ calls shutdown(wait=True), which blocks
    # until EVERY submitted thread finishes — including an abandoned
    # straggler still retrying a dead connection. That would silently
    # defeat the entire point of this function: the caller would still
    # block on the straggler, just at the end of this function instead of
    # inside its own attempt. shutdown(wait=False) below returns as soon as
    # every NON-abandoned future has resolved, leaving any abandoned
    # thread(s) to finish entirely on their own — bounded, not indefinite,
    # since every board passes timeout=TIMEOUT (30s) per request and
    # make_session()'s Retry caps total attempts at 4, so one board's own
    # fetch_jobs() naturally gives up within a few minutes even against a
    # fully dead host. NOTE: ThreadPoolExecutor's worker threads are NOT
    # daemon threads (confirmed: a stdlib ThreadPoolExecutor always creates
    # them non-daemon) — so an abandoned thread still delays the Python
    # process's own final exit by however long it takes to naturally time
    # out, even after every shard's scrape/write/summarize work is done.
    # That's an accepted tradeoff, not a hang: bounded by the request-level
    # timeouts above, and it no longer blocks this function's caller from
    # making progress on the REST of the batch/shard in the meantime.
    pool = ThreadPoolExecutor(max_workers=workers)
    submitted_at: dict[Future[list[Job] | None], float] = {}
    attempt_number: dict[Future[list[Job] | None], int] = {}
    future_company: dict[Future[list[Job] | None], CompanyConfig] = {}

    def submit(company_cfg: CompanyConfig, attempt: int) -> Future[list[Job] | None]:
        f = pool.submit(scrape_one, company_cfg)
        submitted_at[f] = time.monotonic()
        attempt_number[f] = attempt
        future_company[f] = company_cfg
        return f

    for c in companies:
        submit(c, attempt=1)

    # Only LIVE (non-abandoned) futures ever sit in `pending` — this is
    # deliberately a different set from `abandoned` rather than one
    # combined collection, because concurrent.futures.wait()'s `not_done`
    # return value has no concept of "abandoned": it reports a future as
    # not-done for as long as its thread is still actually running, so a
    # naive `while pending:` loop built directly on wait()'s own
    # done/not_done sets would never terminate while a genuinely stuck
    # abandoned attempt keeps running — confirmed live on prod: a trial
    # hung indefinitely (all companies had long since scraped) because two
    # abandoned Workday attempts were still slowly finishing in the
    # background, and got handed straight back into `pending` by every
    # subsequent wait() call. Removing an abandoned future from `pending`
    # for good, right when it's abandoned, is what makes the loop's own
    # progress independent of how long an abandoned attempt keeps running.
    pending = set(submitted_at)
    try:
        while pending:
            done, still_pending = wait(pending, timeout=poll_interval, return_when=FIRST_COMPLETED)
            now = time.monotonic()

            for f in done:
                company_cfg = future_company[f]
                completed_names.add(company_cfg["name"])
                results.append(f.result())

            # Every STILL-pending future that's now past the timeout gets a
            # fresh attempt submitted behind it, unless it's already used
            # up its requeue budget — in which case it's left to run in
            # the background (still occupying a worker slot) and simply
            # never contributes a result, i.e. counted as failed once
            # every other future has resolved. Either way it's removed
            # from `still_pending` here — once abandoned, a future is
            # never waited on again, regardless of how long it keeps
            # running (see the comment above `pending = set(...)`).
            for f in list(still_pending):
                if now - submitted_at[f] < per_company_timeout_s:
                    continue
                company_cfg = future_company[f]
                attempt = attempt_number[f]
                abandoned.add(f)
                still_pending.discard(f)
                if attempt >= MAX_REQUEUE_ATTEMPTS:
                    log.warning(
                        "%s: still running after %d attempt(s) over %.0fs — "
                        "giving up on this batch (left running in the "
                        "background; will not block the rest of the shard)",
                        company_cfg["name"],
                        attempt,
                        per_company_timeout_s,
                    )
                    completed_names.add(company_cfg["name"])
                    results.append(None)
                    continue
                log.warning(
                    "%s: still running after %.0fs — requeuing a fresh "
                    "attempt (%d/%d) behind the rest of the batch instead "
                    "of blocking on it",
                    company_cfg["name"],
                    per_company_timeout_s,
                    attempt + 1,
                    MAX_REQUEUE_ATTEMPTS,
                )
                still_pending.add(submit(company_cfg, attempt=attempt + 1))
            pending = still_pending
        pool.shutdown(wait=False)
        return completed_names, results, False
    except KeyboardInterrupt:
        log.warning(
            "Interrupted — %d/%d companies had already finished scraping; "
            "saving their results instead of discarding the run",
            len(results),
            len(companies),
        )
        pool.shutdown(wait=False, cancel_futures=True)
        return completed_names, results, True


def _run_batch(
    companies: list[CompanyConfig],
    *,
    company: str | None,
    limit: int | None,
    database: str | None,
    concurrency: int | None,
    no_detail_cache: bool,
    deps: RunDeps,
    config: ConfigFile,
    run_started: float,
    shard_scope: set[str] | None,
    per_company_timeout_s: float | None,
) -> int:
    """Scrape, diff, write, and summarize exactly this batch of companies.

    Factored out of run() so a full run can be split into several smaller
    batches (--shard-size) that each scrape/diff/write/summarize
    independently, instead of one pass across every configured company that
    holds the entire previous+current pool in memory for the whole run and
    writes it all in a single transaction at the very end. See
    scraper/db.py's write_jobs()/load_previous() `scope_companies`/
    `company_names` parameters, which this function's `shard_scope` drives.

    shard_scope=None means "this batch is the whole configured pool" — the
    original, unsharded behavior (run() with no --shard-size, or a
    --company on-demand refresh, both pass None here and get the exact
    prior full-replace write/load semantics). shard_scope=<names> means
    "this batch is one shard of a larger sharded run" — previous state and
    the write are both scoped to just this shard's companies, so neither
    this batch's memory footprint nor a failure in it touches any other
    shard.

    Return value matches run()'s own contract (0 success, 1 hard failure,
    130 interrupted) for exactly this batch.
    """
    settings: dict[str, object] = {}

    log.info("Scraping %d compan%s...", len(companies), "y" if len(companies) == 1 else "ies")

    # previous drives new-job detection, first_seen carryover, and each
    # board's detail-fetch cache (BaseScraper._cached_detail) — read from
    # --database (whatever write_jobs() last wrote there). --limit is a smoke
    # test that must never touch the real database in either direction (same
    # contract as write_jobs() below being skipped for --limit) — even a
    # read would create the file via metadata.create_all(), so it's skipped
    # here too.
    if database and limit is None:
        previous = deps.load_previous(database, shard_scope)
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
    # Emptying `previous` outright instead would be a bug: every job's
    # first_seen would reset (and posted_date with it, since db.py derives it
    # from first_seen), and diff() would report the entire pool as new.
    scraper_previous: dict[str, Job] = {} if no_detail_cache else previous
    if no_detail_cache:
        log.info(
            "--no-detail-cache: re-fetching every posting's detail page "
            "(first_seen/diff still use the %d known jobs)",
            len(previous),
        )

    def scrape_one(company_cfg: CompanyConfig) -> list[Job] | None:
        """Scrape a single company; None signals failure (logged, never fatal)."""
        board = company_cfg["board"]
        scraper_cls = deps.scrapers.get(board)
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

    workers = concurrency if concurrency is not None else DEFAULT_CONCURRENCY
    scrape_started = time.monotonic()
    completed_names, results, interrupted = _scrape_companies(
        companies, scrape_one, workers=workers, per_company_timeout_s=per_company_timeout_s
    )
    log.debug("Scrape phase took %.1fs total", time.monotonic() - scrape_started)

    failures = sum(1 for r in results if r is None)
    current: list[Job] = [job for r in results if r is not None for job in r]
    log.info(
        "Scraped %d jobs across %d companies (%d scrape failures)",
        len(current),
        len(results),
        failures,
    )

    # No age filtering — every currently-listed posting is stored, every
    # run. A job leaves the pool once a fresh scrape's listing no longer
    # includes it (closed/filled/expired), not because it crossed a fixed
    # day count: --database is a full-replace write of exactly
    # `full_current` below.
    if limit is not None:
        log.info(
            "--limit %d applied: capping %d jobs down to %d",
            limit,
            len(current),
            min(limit, len(current)),
        )
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

    # Carry over first_seen and role_summary for jobs we already knew about;
    # stamp first_seen for jobs we're seeing for the first time. Every board
    # scraper builds a fresh Job() each run (first_seen="" and role_summary=""
    # by dataclass default) — without the carryover half, every already-known
    # job's previously generated summary would be silently overwritten with
    # "" on the next write, even though the summarize step correctly never
    # re-requests it (same failure mode Job.posted_date already documents and
    # guards against). Without the stamping half, first_seen would stay ""
    # forever: db.py's _posted_date() requires a truthy first_seen to derive
    # posted_date from a board's posted_days, so an unstamped new job is
    # written with posted_date=NULL and — since load_previous() round-trips
    # both fields unchanged — never self-heals on a later run either.
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for job in current:
        if job.id in previous:
            job.first_seen = previous[job.id].first_seen
            job.role_summary = previous[job.id].role_summary
        else:
            job.first_seen = now

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

    if limit is not None:
        # --limit truncates the scraped list arbitrarily — writing that as
        # the full snapshot would discard jobs it never even considered, and
        # this is a smoke test, not a real run. Skip the write.
        log.info("--limit set — skipping database write (%d jobs)", len(full_current))
        return 0

    # --database is the only sink now (docs/jobs.json is gone), so a failed
    # write here means this run's results are lost — write_jobs() reports
    # success/failure explicitly rather than swallowing it, and this run
    # must fail loudly (non-zero exit) when it does, or a caller like
    # main.py's --jobscraper-pipeline sees exit 0 and proceeds to
    # ingest/parse against unchanged data (confirmed happening in practice
    # 2026-08-14 before this check existed).
    #
    # Retried here (not inside write_jobs() itself, to keep its own
    # transaction/atomicity semantics unchanged): the scraper can itself be
    # the one starved by a concurrent Node/daemon write against the shared
    # data/app.db file, in which case a purely transient SQLITE_BUSY
    # shouldn't discard an entire run's results — see GitHub issue #38.
    assert database is not None  # guaranteed by the --database-required check above
    write_succeeded = False
    write_attempts = 3
    for attempt in range(1, write_attempts + 1):
        write_succeeded = deps.write_jobs(
            database, full_current, {j.id for j in new_jobs}, scope_companies=shard_scope
        )
        if write_succeeded:
            break
        if attempt < write_attempts:
            backoff = 2 * attempt
            log.warning(
                "Database write attempt %d/%d failed — retrying in %ds",
                attempt,
                write_attempts,
                backoff,
            )
            time.sleep(backoff)
    if not write_succeeded:
        log.error("Database write failed — run's results were NOT persisted")
        return 1

    # Passive WAL checkpoint after the write's own transactions have closed —
    # backstop against the WAL growing unbounded (see checkpoint_wal()'s
    # docstring). Best-effort: failure here doesn't fail the run, since the
    # write itself already succeeded.
    deps.checkpoint_wal(database)

    # AI role summaries are no longer generated here. Live per-job
    # summarize_role() calls during scrape were the direct cause of hitting
    # provider usage limits quickly (called for every single newly-diffed
    # job, sequentially, with no batching/caching) and, on a degraded/failing
    # provider, of materially extending scrape runtime (confirmed in
    # practice on prod: hundreds of sequential blocking HTTP round-trips,
    # each retried across two providers, on a run where both providers were
    # failing). role_summary is now populated entirely by backlog batch
    # inference against the parent job_pipeline's own fine-tuned model (see
    # job_pipeline/scripts/run_kaggle_role_summary_inference.py) — jobs land
    # here with an empty role_summary and get filled in later out-of-band.
    # update_role_summary (scraper/db.py) and the carry-forward-for-known-
    # jobs behavior below are unchanged — role_summary set any other way
    # (this backlog path, or a manual patch) still isn't lost on a
    # subsequent scrape.

    if interrupted:
        log.warning(
            "Run interrupted after %.1fs — saved %d/%d companies scraped before "
            "Ctrl-C, remaining companies carried forward unchanged from the "
            "previous snapshot",
            time.monotonic() - run_started,
            len(completed_names),
            len(companies),
        )
        # 130 = 128+SIGINT, the conventional shell exit code for
        # Ctrl-C — distinguishes "interrupted, partial save" from both a
        # clean run (0) and a hard failure (1) for any caller checking the
        # exit code (e.g. main.py's --jobscraper-pipeline).
        return 130

    return 0


def _shard(companies: list[CompanyConfig], shard_size: int | None) -> list[list[CompanyConfig]]:
    """Split `companies` into consecutive shard_size-sized batches, in their
    existing config.json order. shard_size=None (or >= len(companies))
    returns a single shard containing everything — the original, unsharded
    behavior."""
    if not shard_size or shard_size >= len(companies):
        return [companies]
    return [companies[i : i + shard_size] for i in range(0, len(companies), shard_size)]


def run(
    company: str | None = None,
    limit: int | None = None,
    verbose: bool = False,
    database: str | None = None,
    concurrency: int | None = None,
    no_detail_cache: bool = False,
    llm_provider: str | None = None,
    shard_size: int | None = None,
    per_company_timeout_s: float | None = DEFAULT_PER_COMPANY_TIMEOUT_S,
    deps: RunDeps | None = None,
) -> int:
    """Load config, resolve which companies to scrape, and run them as one
    or more independent batches (see _run_batch).

    shard_size splits a full run (no --company) into consecutive batches of
    at most that many companies, each scraped/diffed/written/summarized on
    its own — see _run_batch's docstring for why: bounding peak memory to
    one shard's previous+current job set instead of the whole pool's, and
    containing a batch's failure/timeout to just that batch instead of
    losing an entire run's results. Default (None): a single shard holding
    every company, which is exactly the original unsharded behavior — every
    existing caller (including --company, which always gets its own single
    unscoped batch regardless of shard_size) is unaffected unless it opts
    in.

    per_company_timeout_s bounds how long any one company's scrape may run
    before a fresh attempt is requeued behind it — see _scrape_companies'
    docstring for the full mechanics (a stalled attempt is never killed,
    just abandoned and superseded). Defaults ON (DEFAULT_PER_COMPANY_TIMEOUT_S)
    since a single hanging company blocking an entire batch/shard is exactly
    the failure mode this whole run() restructuring exists to contain; pass
    None to fall back to the original unbounded per-company wait.

    Returns the highest-severity exit code across all shards: 1 (hard
    failure) beats 130 (interrupted) beats 0 (success) — a caller checking
    the exit code must see a failure/interruption in ANY shard, not just
    the last one. An interrupt during one shard's scrape does not abort
    remaining shards; consistent with a single-shard run's own
    "interrupted" contract of saving what finished and returning 130 rather
    than raising, this loop keeps going so unaffected shards still get their
    normal scrape instead of being skipped because of the interrupt.
    """
    deps = deps or RunDeps()
    _configure_log_level(verbose)
    if llm_provider:
        # scraper/summarize.py reads this to pin to one provider instead of
        # its default try-Anthropic-then-Ollama fallback.
        os.environ["LLM_PROVIDER"] = llm_provider
    run_started = time.monotonic()
    log.debug("Config path: %s", deps.config_path)

    config: ConfigFile = json.loads(deps.config_path.read_text(encoding="utf-8"))
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

    all_companies = config["companies"]
    if company is not None:
        selected = [c for c in all_companies if c["name"] == company]
        if not selected:
            log.error("No configured company named %r", company)
            return 1
        # --company is always its own single unscoped batch — sharding only
        # applies to a full run across every configured company.
        shards = [selected]
        shard_scopes: list[set[str] | None] = [None]
    else:
        shards = _shard(all_companies, shard_size)
        if len(shards) > 1:
            log.info(
                "--shard-size %d: splitting %d companies into %d batches",
                shard_size,
                len(all_companies),
                len(shards),
            )
        # A single shard covering the whole pool keeps the original
        # unscoped full-replace write/load (shard_scope=None) — only a
        # genuinely multi-shard run scopes each batch's write/load to its
        # own companies.
        shard_scopes = (
            [None] if len(shards) == 1 else [{c["name"] for c in batch} for batch in shards]
        )

    exit_code = 0
    for batch, scope in zip(shards, shard_scopes):
        batch_code = _run_batch(
            batch,
            company=company,
            limit=limit,
            database=database,
            concurrency=concurrency,
            no_detail_cache=no_detail_cache,
            deps=deps,
            config=config,
            run_started=run_started,
            shard_scope=scope,
            per_company_timeout_s=per_company_timeout_s,
        )
        # Worst-severity-wins: 1 > 130 > 0, so one shard's hard failure is
        # never masked by a later shard's clean 0, and an interruption is
        # never masked by a later shard finishing normally.
        if batch_code == 1:
            exit_code = 1
        elif batch_code == 130 and exit_code == 0:
            exit_code = 130

    log.info("Run finished in %.1fs", time.monotonic() - run_started)
    return exit_code


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
        help="pin scraper/backfill_blurbs.py's AI company blurbs to just this "
        "one provider — the other is never attempted, so a failure returns "
        "'' instead of silently falling back. Has no effect on this scrape "
        "run itself (role_summary is no longer generated here). Default: "
        "try Anthropic first, fall back to Ollama if it's unconfigured or fails.",
    )
    parser.add_argument(
        "--shard-size",
        type=int,
        help="split a full run (ignored when --company is set) into consecutive "
        "batches of at most this many companies, each scraped/diffed/written/"
        "summarized independently instead of one pass across every configured "
        "company. Bounds peak memory to one shard's previous+current job set "
        "instead of the whole pool's, and contains a batch's failure/timeout "
        "to just that batch instead of losing an entire run's results — see "
        "scraper/db.py's write_jobs()/load_previous() scope_companies/"
        "company_names parameters. Default (unset): a single shard covering "
        "every company, i.e. the original unsharded behavior.",
    )
    parser.add_argument(
        "--per-company-timeout",
        type=float,
        default=DEFAULT_PER_COMPANY_TIMEOUT_S,
        help="seconds a single company's scrape may run before a fresh attempt "
        "is requeued behind it instead of letting it block the rest of the "
        f"batch (default {DEFAULT_PER_COMPANY_TIMEOUT_S:.0f}s). The original, "
        "stalled attempt is never killed (Python can't safely interrupt a "
        "worker thread mid-request) — it's abandoned and its eventual result "
        "discarded, costing one worker slot until it finishes on its own. A "
        f"company that stalls past this timeout {MAX_REQUEUE_ATTEMPTS} times "
        "in a row is left running in the background and counted as failed "
        "for this batch rather than requeued forever. Pass 0 or a negative "
        "number to disable and wait on every company unboundedly instead "
        "(the original behavior).",
    )
    args = parser.parse_args()
    exit_code = run(
        company=args.company,
        limit=args.limit,
        verbose=args.verbose,
        database=args.database,
        concurrency=args.concurrency,
        no_detail_cache=args.no_detail_cache,
        llm_provider=args.llm_provider,
        shard_size=args.shard_size,
        per_company_timeout_s=(args.per_company_timeout if args.per_company_timeout > 0 else None),
    )
    # os._exit() instead of sys.exit(): a requeued/abandoned company (see
    # _scrape_companies) can leave a non-daemon worker thread still
    # retrying a dead connection — stdlib ThreadPoolExecutor threads are
    # never daemon threads, so a plain interpreter shutdown (which sys.exit
    # triggers) blocks joining that thread, delaying this process's actual
    # exit by however long that abandoned request takes to naturally time
    # out (bounded by each board's own request timeout/retry count — a few
    # minutes at worst, not indefinite, but still pure waste once every
    # shard's real work — scrape, diff, write, summarize — is already done
    # and this process has nothing left to do). Confirmed live: a run with
    # one genuinely unreachable company took 2.5+ minutes just to exit after
    # its last useful log line, purely waiting on that thread. Safe here
    # specifically because this is the __main__ CLI entrypoint, not the
    # importable run() function — jobs/scraper_runner.py (the real caller
    # on prod) always launches this as its own `python -m scraper.main`
    # subprocess, so skipping normal interpreter teardown here can't affect
    # any other Python state; run() itself is untouched and still returns
    # normally for tests/embedders that don't want a hard process exit.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)


if __name__ == "__main__":
    main()
