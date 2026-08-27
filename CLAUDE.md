# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A job pool generator, meant to be consumed by other apps:
- A **Python scraper** ([scraper/](scraper/)) polls company career pages (Workday, Greenhouse, Rippling, BambooHR, Ashby, Breezy, Lever, SmartRecruiters, Recruitee, Personio, USAJobs, Workable, Teamtailor)
- Every currently-listed posting is stored **unfiltered** in `--database` — no keyword/title/location/age curation. Consumer apps are expected to filter/match for their own use case downstream; `config.json`'s `criteria` (`keywords`/`blacklist_keywords`) is kept only as a reference keyword bank for those consumers, not applied by the pipeline itself. A job leaves the pool only once a fresh scrape's listing no longer includes it — `--database` is a full-replace write of exactly the current run's results, not an accumulating log
- `python -m scraper.main --company "Acme"` scrapes and merges just one company's fresh listings into the pool on demand, without waiting for the next scheduled run

No server is involved. The original design doc is [Job_Scraper.md](Job_Scraper.md) (historical — predates the shift away from Discord notifications, storage filtering, and the `docs/jobs.json` snapshot described here).

**`docs/jobs.json` is no longer written.** This pipeline used to write a static JSON snapshot for a GitHub Pages dashboard ([docs/](docs/) — `index.html`/`app.js`/`store.js`) and the hourly cron in [.github/workflows/scrape.yml](.github/workflows/scrape.yml) that scraped and committed it. `--database` (a real SQL sink, see below) fully replaced that role once it existed, so the JSON write was pure wasted I/O — removed. The dashboard files and workflow are left in place but now unmaintained/stale (frozen at whatever `docs/jobs.json` last held); [docs/API.md](docs/API.md) documents that now-frozen file's historical schema, not a live feed.

## Commands

```
python -m pytest                       # run all tests
python -m pytest tests/test_workday.py # run one test file
python -m scraper.main --database "sqlite:///jobs.db"  # full run (ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN optional)
python -m scraper.main --company "Acme" --database "sqlite:///jobs.db"       # on-demand refresh: scrape + merge just this company
python -m scraper.main --company "Acme" --limit 1 --verbose  # smoke test one job, full DEBUG detail, skips the write (no --database needed)
python -m scraper.main --database "postgresql+psycopg2://user:pass@host/db"  # any SQLAlchemy URL
python -m scraper.main --database "sqlite:///jobs.db" --concurrency 16       # scrape more companies in parallel (default 16)
python -m scraper.main --database "sqlite:///../data/jobs.db" --no-detail-cache  # one-time backfill: re-fetch every detail page
python -m scraper.main --database "sqlite:///jobs.db" --llm-provider ollama  # pin AI summaries to just Ollama (skip Anthropic entirely)
python -m scraper.backfill_blurbs      # one-time: generate company blurbs into config.json (needs ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN)
pip install -r requirements.txt        # deps (requests, anthropic, sqlalchemy; pytest + responses for dev)
```

## Architecture

Pipeline in [scraper/main.py](scraper/main.py): load config → run each company's scraper (failures logged, never fatal) → diff against the previous run's state (read from `--database` via `load_previous()` — see the `--database` entry below) → summarize new jobs via Anthropic/Ollama (optional, best-effort) → write the full pool to `--database`.

- **`Job.id` is the diff key** (`{company_slug}:{requisition_id}`) — must be stable across runs or everything looks "new" in the diff.
- **`--database` is required** for a real run — it's the only sink, so without it there'd be nowhere to write the results (fails fast with an error). The one exception is **`--limit N`**, a smoke test that caps the scraped list and skips the database read/write entirely (a truncated list isn't a valid full snapshot to persist).
- **`--company "Name"`** scopes a run to one company, merging its freshly scraped jobs into the previous run's full job set (everyone else's jobs pass through unchanged) — the on-demand refresh path for consumer apps. The merge source ("everyone else's prior jobs") is `load_previous()`'s read of `--database`.
- **Logging**: default (INFO) output covers one line per company scraped, diff counts. Pass `--verbose` (or set `LOG_LEVEL=DEBUG`) for per-request/per-page detail from each board scraper, AI summary attempts (`scraper.summarize`), and stage timing — useful when a run's behavior isn't obvious from the default output alone.
- **`--database "<SQLAlchemy URL>"`** ([scraper/db.py](scraper/db.py)): the pipeline's only sink. `scraper/main.py`'s own `previous` state (new-job detection, `first_seen` carryover, each board's per-job detail-fetch cache — see `BaseScraper._cached_detail()`) is also read from here via `load_previous()`. The URL's dialect (`sqlite://`, `postgresql+psycopg2://`, `mysql+pymysql://`, …) picks the backend; no per-database adapter code is needed since SQLAlchemy handles that. Only SQLite's driver ships with the stdlib — Postgres/MySQL/etc. need their driver package installed separately. Schema is normalized across four tables (`companies`, `sources`, `jobs`, `job_locations`) rather than one flat table — `company`/`source` are low-cardinality strings repeated on every job, `company_blurb` is a per-company attribute, and a job's `locations` is a genuine one-to-many, so each gets its own table instead of a JSON-encoded column. Location text is stored exactly as scraped, no dedup of spelling/format variants. Each run does a full delete+reinsert of every table (full-replace semantics, not an incremental upsert); companies/sources are looked-up-or-inserted by name so repeated values across jobs don't duplicate rows. Best-effort like the AI summaries in the sense that a failure is logged rather than raising an unhandled exception — but since this is now the *only* sink, a failed write does mean that run's results are lost (unlike when `docs/jobs.json` was a second, always-on copy). Skipped entirely whenever `--limit` is set.
- **Per-job detail-fetch caching** (`workday`, `rippling`, `bamboohr`, `smartrecruiters` — the four boards with a per-posting detail HTTP call): each board's list endpoint still runs every time (how new/removed postings get detected), but the expensive per-job detail GET (description; for `workday` also multi-location expansion; for `smartrecruiters` also the posting URL) is skipped for any posting whose id was already in `previous` — reusing that job's cached detail fields via `BaseScraper._cached_detail(job_id)` instead of re-fetching. `title`/`posted_on`/`posted_days`/other list-sourced fields always come from the current run's list response regardless — only the detail-only fields get reused. This only has any effect when `--database` is passed (see above), since that's what populates `previous`.
- **`--no-detail-cache`** bypasses that cache for one run: every posting's detail page is re-fetched even if its id is already known. This exists because the cache makes a stale description permanent — a job scraped under the old 1500-char truncation cap keeps that truncated text forever, since its detail page is never fetched again. It withholds `previous` from the **scrapers only**; `first_seen` carryover and `diff()`'s new-job detection still use the real `previous`. Emptying `previous` outright instead (e.g. by omitting `--database`) would reset every `first_seen` — and `posted_date` with it, since [scraper/db.py](scraper/db.py) derives it from `first_seen` — and make `diff()` report the entire pool as new, firing an AI role summary for every job. Roughly one extra HTTP request per known job on the four detail-fetch boards, so this is a one-time backfill tool, not for routine runs.
- **Descriptions are not truncated.** `html_to_text()`'s `max_chars` defaults to `None`; it used to default to 1500, and `ashby`/`lever` each had their own separate `[:1500]` slice on the `descriptionPlain` path that bypassed `html_to_text` entirely. All three are gone. Downstream consumers parse these descriptions for skills/requirements, and that content routinely sits past the 1500th character. Callers wanting a bounded string (a preview, an LLM prompt with a token budget) pass `max_chars` explicitly — bound the consumer, not the stored text.
- **`--concurrency N`** (default 16): number of companies scraped in parallel via `ThreadPoolExecutor` in `main.py`. Safe to raise because (a) each company mostly hits a distinct host (its own Workday tenant, Greenhouse token, etc.), so concurrency scales cross-host throughput rather than the request rate against any single host, and (b) every board's `requests.Session` is built via `make_session()` (below), which retries transient failures instead of failing the whole company outright.
- **Retry/backoff on every board request** ([scraper/boards/base.py](scraper/boards/base.py) `make_session()`): all board scrapers build their `requests.Session` through this helper instead of `requests.Session()` directly. It mounts an `HTTPAdapter` with a `urllib3.Retry` (`total=4`, exponential backoff starting at 1.5s, retries on `429`/`500`/`502`/`503`/`504`, honors `Retry-After`). This is why a transient rate limit (e.g. Workday tenants 429ing under load) no longer drops that company's entire scrape for the run — `scrape_one`'s broad `except Exception` in `main.py` is still the final safety net once retries are exhausted.

## Adding Companies and Job Boards

**Company already on Workday** → config only, no code. Add an entry to `companies` in [config.json](config.json). To find a company's url: open their careers page → F12 → Network → XHR → click "show more jobs" → copy the POST URL. The pattern is `…/wday/cxs/<company>/<tenant>/jobs`. Set `careers_base` to the public careers page base (e.g. `https://<company>.wd<N>.myworkdayjobs.com/en-US/<tenant>`) — job links are built as `careers_base + externalPath`.

**Different job board entirely** → one new file in [scraper/boards/](scraper/boards/): subclass `BaseScraper`, implement `fetch_jobs()`, register in `SCRAPERS` in [scraper/boards/\_\_init\_\_.py](scraper/boards/__init__.py). `main.py` never imports concrete scrapers. Use `self.slug` (from `slugify` in [base.py](scraper/boards/base.py)) for the `Job.id` prefix.

**Supported boards** (config `"board"` value + its required fields):
- `workday` — `url` + `careers_base`
- `greenhouse` — `token`; list-only, real posting date from `first_published`
- `rippling` — `board_id`; list-only, **date-less** (`posted_days=None`)
- `bamboohr` — `company` (subdomain); list-only, **date-less**
- `ashby` — `slug`; list-only, real posting date from `publishedAt`
- `breezy` — `company` (subdomain); list-only, real posting date from `published_date`
- `lever` — `company` (slug); list-only, real posting date from `createdAt`
- `smartrecruiters` — `company` (identifier); real posting date from `releasedDate`, but **one detail GET per job** (like `bamboohr`/`rippling`) since the list endpoint doesn't expose a description or posting URL
- `recruitee` — `company` (subdomain); list-only, real posting date from `published_at`
- `personio` — `company` (subdomain); list-only, **XML feed** (not JSON), real posting date from `createdAt`
- `usajobs` — no config beyond `board`+`name`; needs `USAJOBS_API_KEY`/`USAJOBS_USER_AGENT` env vars (free self-service key from developer.usajobs.gov — the only board that requires credentials); list-only, real posting date from `PublicationStartDate`. **The one nationwide, not per-employer, board**: `Job.company` is set per-job from the API's own `OrganizationName` (the hiring agency), not from the config entry's `name`. Missing credentials are treated like any other board-scrape failure — logs a warning and returns no jobs, never fatal to the run.
- `workable` — `company` (account slug); list-only, real posting date from `published_on`
- `teamtailor` — `company` (subdomain slug); list-only, real posting date from `date_published`

All boards store every listing they fetch — there is no keyword, title, location, or age filtering in the pipeline. `greenhouse`/`rippling`/`bamboohr`/`ashby`/`breezy`/`lever`/`recruitee`/`personio`/`usajobs`/`workable`/`teamtailor` use list endpoints only (no per-job detail) to stay cheap; `smartrecruiters` is the exception, needing a detail call for description/URL. This is a cost control, unrelated to filtering.

**Dates**: Workday/Greenhouse/Ashby/Breezy (and most other boards) provide a posting date → `posted_days`, parsed at scrape time (used to derive `posted_date`, not to filter). Rippling/BambooHR don't expose a date cheaply → `posted_days=None`; consumers fall back to `first_seen` for age in that case (the now-stale dashboard's own convention was hiding date-less jobs >6 days after first seen — see [docs/app.js](docs/app.js) `effectiveAge` — but that's a display concern, separate from the pipeline's own storage, which applies no cutoff). Some individual Workday tenants omit `postedOn` from the list response even though they're not otherwise a date-less board (confirmed on Parsons, 2026-08) — `scraper/boards/workday.py`'s `fetch_jobs()` falls back to the same field on the job's detail page when that happens, but only for newly-discovered jobs (see `_posted_date()` in `scraper/db.py`, which preserves a job's first-derived `posted_date` forever once set).

**Adding a board**: add the config entry, run `python -m scraper.main --company "New Company" --database "<url>"` locally to merge just its listings into the pool.

**Adding a company blurb**: after adding a company entry, either run `python -m scraper.backfill_blurbs` (only touches entries missing a `"blurb"`, so it's safe to run repeatedly) or hand-write a short `"blurb"` value directly into the entry. See "AI Summaries and Company Blurbs" below.

## AI Summaries and Company Blurbs

`ANTHROPIC_API_KEY` is optional — the pipeline and dashboard work fully without it; descriptions still populate (they're board-sourced, no AI dependency), summaries and blurbs just stay blank (`""`). `ANTHROPIC_AUTH_TOKEN` (e.g. a Claude Code OAuth token, useful for local runs without provisioning a separate API key) works as an alternative — `ANTHROPIC_API_KEY` takes precedence if both are set.

`OLLAMA_API_KEY` (Ollama Cloud, free tier) is an optional second fallback, tried whenever Anthropic is unconfigured or its call fails — e.g. an expired `ANTHROPIC_AUTH_TOKEN`. Uses `gemma4:31b`, a non-reasoning model on the free tier — most other free-tier-available models on Ollama Cloud are reasoning models (return a `thinking` block before the answer), unnecessary latency/tokens for a 1-2 sentence summary; most of the *larger* catalog models (`qwen3.5:397b`, `kimi-k*`, `glm-5.*`, `deepseek-v4-pro`, `mistral-large-3`, `minimax-*`) 403 on the free tier entirely ("requires a subscription"). The free tier is concurrency-limited (2 concurrent requests, queue of 5, confirmed via the API's own `x-ratelimit-*` response headers), not a requests/minute counter — irrelevant in practice since both helpers below are only ever called sequentially, one job/company at a time.

**Key rotation** ([scraper/ollama_keys.py](scraper/ollama_keys.py)): `OLLAMA_API_KEY` may hold several comma-separated keys — set this way specifically to survive Ollama Cloud's free-tier **hourly usage limit** (a distinct, harder cap than the concurrency limit above — confirmed via Ollama's own 429 body text: `"you've reached your hourly usage limit, please wait or upgrade to continue"`, vs. `"too many concurrent requests"` for the transient one). A hit on the hourly-limit marker specifically rotates immediately to the next comma-separated key (no wait, unlike the existing transient-429 retry, which keeps using the same key); a full pass through every key that's not currently cooling down happens before giving up and returning `""`. Rotation state (which key is exhausted, until when — a ~5h cooldown per Ollama's own session-limit window, not literally 60 minutes) is **persisted to `../data/ollama_key_rotation.json`** rather than kept in memory, shared with the parent pipeline's own port at `job_pipeline/utils/ollama_keys.py` — this repo is normally checked out nested inside that pipeline (see `main.py --run-jobscraper`), and both this repo's scrape (its own process) and the parent's job-parsing (a different process) hit the same 4 keys against the same quota, so a key one process learns is exhausted must be respected by the other immediately, not rediscovered independently. Falls back to a local `.ollama_key_rotation.json` in this repo if run fully standalone (this repo's own GitHub Actions cron, no parent `../data/` present) — rotation still works, just isn't cross-process-shared, which doesn't matter there since there's no other process to share with. Only a short, non-reversible hash of each key is ever written to that file, never the raw secret.

- **Role summaries** (`Job.role_summary`, [scraper/summarize.py](scraper/summarize.py)): generated for every newly-diffed job, so AI cost scales with total new-job volume across all companies each run — not a small curated subset.
- **Company blurbs** (`Job.company_blurb`): generated **once per company**, not per scrape run. `python -m scraper.backfill_blurbs` reads `config.json`, fills in a `"blurb"` field for any company missing one, and writes it back — this is a manual, one-time script, never invoked by `scraper/main.py` or the GitHub Actions workflow. `main.py` then denormalizes each company's cached blurb onto every one of its jobs at snapshot-save time — this is **required**, not a style choice: `config.json` lives at the repo root, GitHub Pages only serves `docs/`, and the dashboard's only network call is `fetch('jobs.json')` — it has no way to read `config.json` directly.
- Both helpers in `scraper/summarize.py` are best-effort across both providers: any failure (missing key, network error, API error) logs a warning and either falls through to the next provider or returns `""` if none are left, rather than raising — matching the board-scraper failure philosophy elsewhere in this pipeline.
- **`--llm-provider {anthropic,ollama}`** (or `LLM_PROVIDER` env var directly) pins to just one provider — the other is never attempted, so a failure returns `""` instead of silently falling back. Useful to confirm which provider actually produced a summary, or to skip a known-broken one (e.g. an expired `ANTHROPIC_AUTH_TOKEN`) without waiting out its failed call every time. Omitted/unset (or `auto`) keeps the default Anthropic-then-Ollama fallback; an unrecognized value is ignored with a warning rather than silently misbehaving.

## The Workday API

Workday exposes an undocumented public API per company:

```
POST https://<company>.wd<N>.myworkdayjobs.com/wday/cxs/<company>/<tenant>/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
```

Response: `{"total": N, "jobPostings": [...]}` — each posting has `title`, `postedOn`, `locationsText`, `externalPath`, `bulletFields` (first element = requisition ID).

**Gotchas**:
- `total` is only returned on the first page (offset 0); later pages report `total: 0`.
- Pagination is capped at 500 jobs per company (`MAX_JOBS` in [scraper/boards/workday.py](scraper/boards/workday.py)) — no early-stop, every page up to that cap is fetched every run.
- Multi-location postings only say "12 Locations" in the list response; the real list comes from the detail endpoint (`GET <url minus /jobs><externalPath>` → `jobPostingInfo.location` + `additionalLocations`).
- The detail endpoint is called **unconditionally for every posting** (not just multi-location ones) to also fetch `jobPostingInfo.jobDescription` — roughly triples request volume versus a list-only scrape, but is the only way to get real description text for Workday jobs.

## UI

**Stale/unmaintained**: the dashboard below no longer receives data — `scraper/main.py` stopped writing `docs/jobs.json` once `--database` became the pipeline's sole sink (see "What This Project Is" above). Left in place as-is, frozen at whatever `docs/jobs.json` last held, rather than deleted.

- Follow the design system in [ui_guideline.md](ui_guideline.md) for all UI work (pure `#000` background, Inter with negative letter-spacing headings, subtle borders, radial glows instead of shadows)
- The dashboard ([docs/index.html](docs/index.html), [docs/style.css](docs/style.css), [docs/app.js](docs/app.js)) is vanilla HTML/CSS/JS with no build step
- `docs/` is the GitHub Pages root (Pages branch deployment only supports root or `/docs`); `docs/jobs.json` is data, not source — no longer written by the scraper (frozen)
- Clicking a job title opens an in-page detail modal (description, AI role summary, company blurb, similar jobs — whichever are populated) instead of redirecting; the original posting is one clearly-labeled click further, via the modal's "View full posting" link. The modal follows the same `[hidden]`-attribute show/hide convention as the existing location multiselect panel — no new show/hide pattern was introduced.

## API

**Stale/unmaintained**, same caveat as the dashboard above: [docs/API.md](docs/API.md) documents the now-frozen `docs/jobs.json`'s historical schema, not a live feed — the actual current pool lives in whatever `--database` was pointed at (see `scraper/db.py`'s schema instead).

## MCP

Context7 is configured in [.mcp.json](.mcp.json) — use it for up-to-date library/API docs.
