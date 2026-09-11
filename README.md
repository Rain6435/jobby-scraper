# jobby-scraper

[![CI](https://github.com/Rain6435/jobby-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/Rain6435/jobby-scraper/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A job pool generator, meant to be consumed by other apps. It polls **1,102
companies** across 37 job-board integrations, stores every currently-listed
posting **unfiltered** in a SQL database, and gets out of the way — no
keyword/title/location/age curation happens in this pipeline.

## What this is (and isn't)

- **No server.** `python -m scraper.main` is a batch job: scrape, diff,
  summarize, write. Run it on a cron, a GitHub Action, or by hand.
- **No filtering.** Every listing every configured company currently has up
  is stored. `config.json`'s `criteria` block (`keywords`/
  `blacklist_keywords`) is kept only as a reference keyword bank for
  downstream consumers — the pipeline itself never applies it.
- **Full-replace, not a log.** `--database` is overwritten each run with
  exactly what that run scraped. A job leaves the pool the moment a fresh
  scrape's listing no longer includes it (closed, filled, expired) — there's
  no history table and no soft-delete.
- **`--database` is the only sink.** Every consumer reads the SQL database
  this pipeline writes to — nothing else in this repo produces data.

## How it works

```
load config.json (1,102 companies)

        │
        ▼
scrape every company in parallel (ThreadPoolExecutor, --concurrency workers,
  default 16) — one board-specific scraper class per company, failures
  logged and skipped, never fatal to the run
        │
        ▼
diff against the previous run's state, read from --database via
  load_previous() — this is also where first_seen carryover and each
  board's per-job detail-fetch cache pull their prior state from
        │
        ▼
best-effort AI role summary for each newly-diffed job
  (Anthropic → Ollama fallback; optional, degrades to "" with no key set)
        │
        ▼
write the full current pool to --database (delete + reinsert every table;
  retried up to 3x on transient SQLITE_BUSY)
```

`Job.id` (`"{company_slug}:{requisition_id}"`) is the stable diff key — it
must stay stable across runs or every job looks new every time.

Every board scraper builds its HTTP session through a shared
`make_session()` helper ([scraper/boards/base.py](scraper/boards/base.py))
that retries transient failures (`429`, `5xx`, connection errors) with
exponential backoff, so one rate-limited career-page host doesn't drop that
company's whole scrape for the run.

## Supported job boards

| Board | Config fields | Notes |
|---|---|---|
| `workday` | `url`, `careers_base` | Real posting date; one detail GET per job (description + multi-location expansion) |
| `greenhouse` | `token` | List-only; real posting date from `first_published` |
| `rippling` | `board_id` | List-only; **date-less** (`posted_days=None`) |
| `bamboohr` | `company` (subdomain) | List-only; **date-less** |
| `ashby` | `slug` | List-only; real posting date from `publishedAt` |
| `breezy` | `company` (subdomain) | List-only; real posting date from `published_date` |
| `lever` | `company` (slug) | List-only; real posting date from `createdAt` |
| `smartrecruiters` | `company` (identifier) | One detail GET per job (list endpoint has no description/URL); real posting date from `releasedDate` |
| `recruitee` | `company` (subdomain) | List-only; real posting date from `published_at` |
| `personio` | `company` (subdomain) | List-only; **XML feed**, not JSON; real posting date from `createdAt` |
| `workable` | `company` (account slug) | List-only; real posting date from `published_on` |
| `teamtailor` | `company` (subdomain slug) | List-only; real posting date from `date_published` |
| `pinpoint` | `company` (subdomain) | List-only; real posting date from `created_at`/`updated_at` |
| `jobvite` | `company_id` (companyEId) | List-only XML feed; real posting date from `date` |
| `jazzhr` | `company` (subdomain) | List-only XML feed; **date-less** (`posted_days=None`) |
| `governmentjobs` | `agency` (agency slug) | List-only RSS feed; real posting date from `pubDate` |
| `usajobs` | none (needs `USAJOBS_API_KEY`/`USAJOBS_USER_AGENT`) | Nationwide, not per-employer — `Job.company` comes from each posting's own hiring agency |
| `reliefweb` | none (open API) | Global humanitarian, not per-employer — `Job.company` comes from each posting's own source organization |
| `oraclecloud` | `tenant` (subdomain or full host), `site_number` (optional) | List-only; keyless Candidate Experience REST API, real posting date from `PostedDate` |
| `successfactors` | `company` (company slug), `domain` (optional) | List-only; Career Site Builder RSS feed, real posting date from `pubDate` |
| `adp` | `cid` (Client ID), `cc_id` (optional) | List-only; static requisition JSON API, real posting date from `postDate` |
| `paylocity` | `guid` (integration GUID) | List-only; public Job Feed V2 JSON API, real posting date from `postedDate` |
| `icims` | `tenant` (subdomain), `domain` (optional) | List-only; streaming candidate search portal HTML, real posting date from `Posted Date` |
| `atlassian` | none (or `category`, `location`, `keyword`) | Single unauthenticated JSON listings endpoint; full descriptions, real posting date from `updatedDate` |
| `shopify` | none (or `location`, `keyword`) | React Router list + `.data` detail routes; real posting date, full descriptions |
| `phenom` | `url` | Server-rendered `phApp.ddo` JSON; real posting date from `postedDate`, used by OpenText, Bell Canada, Air Canada, NASA JPL |
| `jibe` | `tenant` (subdomain) or `url` (base URL) | List-only public JSON search API; full HTML descriptions, real posting date from `create_date`, used by GitHub, PepsiCo, Costco, FedEx |
| `climatebase`, `cma_heritage`, `idc_career_centre`, `cip_planning`, `wp_job_manager` | site-specific | Small one-off integrations for individual job sites |

Current distribution: 296 Greenhouse, 185 Workday, 142 Ashby, 92 BambooHR,
90 SAP SuccessFactors, 74 SmartRecruiters, 50 Lever, 20 GovernmentJobs, 18 Rippling,
15 Phenom, 10 Teamtailor, 10 Pinpoint, 8 Breezy, 8 Workable, 8 Recruitee, 7 JazzHR,
5 Jibe, 4 Oracle Cloud, 4 Personio, custom tech platforms (Google, Amazon, Apple, Microsoft,
Netflix, IBM, TikTok, Atlassian, EA, Valve, Shopify), plus USAJobs, ReliefWeb,
and one-off site integrations.

Descriptions are **never truncated** — downstream consumers parse them for
skills/requirements, and content routinely runs past what an older 1500-char
cap used to allow.


## Getting started

```bash
git clone https://github.com/Rain6435/jobby-scraper.git
cd jobby-scraper
pip install -r requirements.txt
cp .env.example .env   # optional — see Environment variables below
python -m scraper.main --database "sqlite:///jobs.db"
```

A full run scrapes every configured company and writes the result to the
SQLite file `jobs.db` (created automatically — no schema setup needed;
`write_jobs()` runs `metadata.create_all()` on every invocation).

### Environment variables

All optional — the pipeline runs fully without any of them; missing keys
just mean AI summaries/blurbs stay `""`.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables AI role summaries and company blurbs. |
| `ANTHROPIC_AUTH_TOKEN` | Alternative to `ANTHROPIC_API_KEY` (e.g. a Claude Code OAuth token). `ANTHROPIC_API_KEY` wins if both are set. |
| `OLLAMA_API_KEY` | Second fallback for AI summaries (free-tier Ollama Cloud), tried when Anthropic is unconfigured or its call fails. May hold several comma-separated keys for rotation past the hourly usage limit. |
| `USAJOBS_API_KEY` / `USAJOBS_USER_AGENT` | Required only for the `usajobs` board (free key from developer.usajobs.gov). Every other board works without it. |
| `LOG_LEVEL` | `DEBUG`/`INFO`/`WARNING`/`ERROR` (default `INFO`). Same effect as `--verbose` when set to `DEBUG`. |

## CLI usage

```bash
# Full run — scrapes every company, writes to the database
python -m scraper.main --database "sqlite:///jobs.db"

# Any SQLAlchemy URL works — dialect picks the backend, no adapter code needed
python -m scraper.main --database "postgresql+psycopg2://user:pass@host/db"

# On-demand refresh of just one company: scrapes it fresh and merges the
# result into the previous run's full job set (everyone else passes through
# unchanged) — requires --database, both as merge source and sink
python -m scraper.main --company "Acme" --database "sqlite:///jobs.db"

# Smoke test: scrape one job, full DEBUG logging, skip the database
# entirely (read and write) — --limit is the one case --database isn't required
python -m scraper.main --company "Acme" --limit 1 --verbose

# Scrape more companies in parallel (default 16)
python -m scraper.main --database "sqlite:///jobs.db" --concurrency 24

# One-time backfill: re-fetch every posting's detail page instead of reusing
# a cached description (e.g. after raising/removing a truncation cap)
python -m scraper.main --database "sqlite:///jobs.db" --no-detail-cache

# Pin AI summaries to just one provider instead of the default
# Anthropic-then-Ollama fallback
python -m scraper.main --database "sqlite:///jobs.db" --llm-provider ollama
```

| Flag | Effect |
|---|---|
| `--database "<SQLAlchemy URL>"` | **Required** for a real run — the only place results are written, and the source of "previous run" state (diff, `first_seen`, detail-fetch cache). Exempt only when `--limit` is set. |
| `--company "Name"` | Scope the run to one company (must match a `name` in `config.json`); merges its fresh jobs into the existing snapshot instead of rescraping everything. |
| `--limit N` | Cap the scraped list to the first N jobs before diff/summarize; skips the database read *and* write (smoke test — a truncated list isn't a valid full snapshot). |
| `--verbose` | DEBUG-level logging: per-request/per-page detail, AI summary attempts, stage timing. |
| `--concurrency N` | Number of companies scraped in parallel (default 16). Safe to raise — most companies hit distinct hosts, and every board retries transient failures (429/5xx) with backoff. |
| `--no-detail-cache` | Force every posting's detail page to be re-fetched instead of reusing a cached description. One-time backfill tool, not for routine runs — roughly one extra HTTP request per known job on the four detail-fetch boards. |
| `--llm-provider {anthropic,ollama}` | Pin AI summaries/blurbs to just one provider; the other is never attempted, so a failure returns `""` instead of falling back. |

## Database schema

Normalized across several tables rather than one flat table — see
[`scraper/db.py`](scraper/db.py) for the full SQLAlchemy definitions.

- **`companies`** (`id`, `name` unique, `blurb`) — one row per company;
  `blurb` is generated once by `scraper/backfill_blurbs.py` and denormalized
  onto every one of that company's jobs at write time (consumers only ever
  read `--database`, never `config.json`).
- **`sources`** (`id`, `name` unique) — one row per board type.
- **`jobs`** (`id`, `company_id` FK, `source_id` FK, `title`, `url`,
  `posted_date`, `first_seen`, `description`, `role_summary`, `is_new`) —
  `posted_date` is an absolute `"YYYY-MM-DD"` derived once from `first_seen`
  minus `posted_days` at write time (NULL for date-less boards like
  rippling/bamboohr, where consumers fall back to `first_seen`).
- **`locations`** (`id`, `name` unique, `normalized_key`, `city`, `region`,
  `country_code`, `is_remote`, `town_id` FK) — raw location text exactly as
  scraped is the row's identity (spelling/format variants are deliberately
  never merged); structured fields are additive metadata parsed via
  `scraper.location_resolver.parse_location()`.
- **`towns`** — canonical geographic identity sourced from GeoNames
  (`scraper/gazetteer.py`), keyed by `geoname_id`. Kept separate from
  `locations` so multiple raw location strings for the same real place
  ("San Francisco", "San Francisco, CA") can all resolve to one `towns` row
  without touching `locations`' own "never guess, never merge" identity.
- **`job_locations`** — join table (`job_id`, `location_id`, `ordinal`),
  preserving each job's original location order.

Each run does a full delete + reinsert of every table (full-replace
semantics, not an incremental upsert); companies/sources/locations are
looked-up-or-inserted by their unique key so repeated values don't
duplicate rows. Write failures are retried up to 3 times to absorb
transient `SQLITE_BUSY` from a concurrent process sharing the same file.

**SQLite** needs no driver install. **Postgres/MySQL/etc.** need their
driver package installed separately, e.g.:

```bash
pip install psycopg2-binary
python -m scraper.main --database "postgresql+psycopg2://user:pass@host/db"
```

## Adding companies and job boards

**Company already on Workday** → config only, no code. Add an entry to
`companies` in [config.json](config.json). To find a company's URL: open
their careers page → F12 → Network → XHR → click "show more jobs" → copy
the POST URL (pattern: `…/wday/cxs/<company>/<tenant>/jobs`).

**Different job board entirely** → one new file in
[scraper/boards/](scraper/boards/): subclass `BaseScraper`, implement
`fetch_jobs()`, register in `SCRAPERS` in
[scraper/boards/\_\_init\_\_.py](scraper/boards/__init__.py). `main.py`
never imports concrete scrapers.

**Adding a company blurb**: after adding a company entry, run
`python -m scraper.backfill_blurbs` (only touches entries missing a
`"blurb"`, safe to re-run) or hand-write one directly into the entry.

Full details, including per-board gotchas and the Workday API shape, live in
[CLAUDE.md](CLAUDE.md).

## Testing

```bash
python -m pytest                       # run all tests
python -m pytest tests/test_workday.py # run one test file
```

## Project layout

```
scraper/
  main.py           orchestrator: scrape → diff → summarize → write
  db.py             SQLAlchemy schema + load_previous()/write_jobs()
  storage.py        diff() — new-job detection against previous state
  summarize.py      AI role summaries + company blurbs (Anthropic/Ollama)
  backfill_blurbs.py  one-time script: fills missing company blurbs into config.json
  location_resolver.py / town_resolver.py / gazetteer.py
                     location parsing + GeoNames-backed town resolution
  models.py          Job dataclass
  config_types.py    TypedDicts for config.json's shape
  boards/            one scraper class per job board (base.py has the
                     shared BaseScraper + make_session() retry/backoff logic)
tests/               pytest suite, one file per board/module
config.json           809 companies + criteria keyword bank (reference only)
```

## License

MIT — see [LICENSE](LICENSE).
