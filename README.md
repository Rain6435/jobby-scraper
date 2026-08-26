# JobScraper

[![Scrape jobs](https://github.com/Rain6435/jobby-scraper/actions/workflows/scrape.yml/badge.svg)](https://github.com/Rain6435/jobby-scraper/actions/workflows/scrape.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A free, serverless job pool generator. It polls company career pages
(Workday, Greenhouse, Rippling, BambooHR, Ashby, Breezy, Lever,
SmartRecruiters, Recruitee, Personio, USAJobs) hourly via a GitHub Actions
cron job, stores every listing it finds **unfiltered** in a single JSON file,
and publishes that file as both a static API and a browsable dashboard —
all for free, since GitHub Actions minutes and GitHub Pages hosting are
unlimited on public repos.

No backend server, no database required, no hosting bill.

## Live links

- **Dashboard**: https://faradumatin.github.io/JobScraper/
- **Raw JSON API**: https://faradumatin.github.io/JobScraper/jobs.json

## How it works

```
scrape every configured company (parallel, per-board, --concurrency workers,
                                  each board retries transient failures
                                  with backoff)
        │
        ▼
diff against the previous run's state → which jobs are new?
  (read from --database via load_previous(), not docs/jobs.json —
   omit --database and every job looks new every run)
        │
        ▼
best-effort AI role summary for each new job (optional)
        │
        ▼
save docs/jobs.json (committed to the repo every run — the GitHub Pages
                      dashboard's only source of data)
        │
        ▼
mirror the snapshot into a SQL database (--database) — also what the next
run's diff/first_seen/detail-fetch-cache reads back as "previous"
```

Everything scraped is stored — **there is no keyword, title, location, or
age filtering in the pipeline itself.** `config.json`'s `criteria` block
(`keywords`/`blacklist_keywords`) is kept only as a reference keyword bank;
consumer apps are expected to clone/query the data and filter for their own
use case downstream. A job leaves the pool only once a fresh scrape's
listing no longer includes it (closed/filled/expired) — both docs/jobs.json
and --database are full-replace writes of exactly the current run's
results, not an accumulating log.

`Job.id` (`"{company_slug}:{requisition_id}"`) is the stable diff key used to
detect "new since last run" — it must stay stable across scrapes or
everything looks new.

Every board scraper builds its HTTP session through a shared
`make_session()` helper that retries transient failures (`429`, `5xx`,
connection errors) with exponential backoff before giving up — so a
career-page host that briefly rate-limits under load no longer drops that
company's entire scrape for the run.

## Supported job boards

| Board | Config fields | Notes |
|---|---|---|
| `workday` | `url`, `careers_base` | Real posting date; one detail GET per job (for description + multi-location) |
| `greenhouse` | `token` | List-only; real posting date from `first_published` |
| `rippling` | `board_id` | List-only; **date-less** (`posted_days=None`) |
| `bamboohr` | `company` (subdomain) | List-only; **date-less** |
| `ashby` | `slug` | List-only; real posting date from `publishedAt` |
| `breezy` | `company` (subdomain) | List-only; real posting date from `published_date` |
| `lever` | `company` (slug) | List-only; real posting date from `createdAt` |
| `smartrecruiters` | `company` (identifier) | One detail GET per job (list endpoint has no description/URL) |
| `recruitee` | `company` (subdomain) | List-only; real posting date from `published_at` |
| `personio` | `company` (subdomain) | List-only; **XML feed**, not JSON; real posting date from `createdAt` |
| `usajobs` | none (needs `USAJOBS_API_KEY`/`USAJOBS_USER_AGENT` env vars) | Nationwide board — `Job.company` comes from the posting's own hiring agency, not the config entry |

136 companies are currently configured across these boards in
[`config.json`](config.json).

## Getting started

```bash
git clone https://github.com/Rain6435/jobby-scraper.git
cd JobScraper
pip install -r requirements.txt
cp .env.example .env   # optional — see "Environment variables" below
python -m scraper.main
```

A full run scrapes every configured company and writes the result to
[`docs/jobs.json`](docs/jobs.json).

### Environment variables

All optional — the pipeline runs fully without any of them:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables AI role summaries and company blurbs. Without it, those fields just stay `""`. |
| `ANTHROPIC_AUTH_TOKEN` | Alternative to `ANTHROPIC_API_KEY` (e.g. a Claude Code OAuth token). `ANTHROPIC_API_KEY` wins if both are set. |
| `USAJOBS_API_KEY` / `USAJOBS_USER_AGENT` | Required only for the `usajobs` board (free key from developer.usajobs.gov). Every other board scrapes fine without it. |
| `LOG_LEVEL` | `DEBUG`/`INFO`/`WARNING`/`ERROR` (default `INFO`). Same effect as `--verbose` when set to `DEBUG`. |

## CLI usage

```bash
# Full run — scrapes every company, writes docs/jobs.json
python -m scraper.main

# On-demand refresh of just one company, merged into the previous run's
# full job set — requires --database (that's the merge source now, see
# "Database mirror" below); errors immediately without it
python -m scraper.main --company "Acme" --database "sqlite:///jobs.db"

# Smoke test: scrape one job, full debug logging, skip the write (and skip
# the --database requirement — --limit needs neither)
python -m scraper.main --company "Acme" --limit 1 --verbose

# Mirror the full snapshot into a SQL database (any SQLAlchemy URL) — also
# where this pipeline's own new-job detection/first_seen/detail-fetch-cache
# read their previous-run state from, not docs/jobs.json
python -m scraper.main --database "sqlite:///jobs.db"
python -m scraper.main --database "postgresql+psycopg2://user:pass@host/db"

# Scrape more companies in parallel (default 16)
python -m scraper.main --concurrency 24
```

| Flag | Effect |
|---|---|
| `--company "Name"` | Scope the run to one company (must match a `name` in `config.json`); merges its fresh jobs into the existing snapshot instead of rescraping everything. |
| `--limit N` | Cap the scraped list to the first N jobs before diff/summarize; implies skipping the snapshot write (since a truncated list isn't a valid full snapshot). |
| `--verbose` | DEBUG-level logging: per-request/per-page detail, AI summary attempts, stage timing. |
| `--database "<SQLAlchemy URL>"` | Additionally mirror the full snapshot into a SQL database — `docs/jobs.json` is always written regardless, this is purely additive. See [Database mirror](#database-mirror-optional) below. |
| `--concurrency N` | Number of companies scraped in parallel (default 16). Safe to raise — most companies hit distinct hosts, and every board retries transient failures (429/5xx) with backoff instead of failing outright. |

### Database mirror

`--database` lets consumer apps get a queryable SQL copy of the same
snapshot instead of parsing JSON, without this project needing any
per-database adapter code — the URL's SQLAlchemy dialect picks the backend.
It's also no longer purely optional in practice: `scraper/main.py`'s own
new-job detection, `first_seen` carryover, and each board's per-job
detail-fetch cache all read their "previous run" state from `--database`
(`load_previous()` in `scraper/db.py`), not from `docs/jobs.json` — omit it
and every job looks new every run, and no detail fetch gets skipped
(logged as a warning, never fatal; the pipeline still fully works, just
without those optimizations).

```bash
python -m scraper.main --database "sqlite:///jobs.db"
python -m scraper.main --database "postgresql+psycopg2://user:pass@host/dbname"
python -m scraper.main --database "mysql+pymysql://user:pass@host/dbname"
```

- SQLite's driver ships with Python's stdlib; Postgres/MySQL/etc. need their
  driver package installed separately (e.g. `pip install psycopg2-binary`).
- Each run fully replaces every table's contents (delete + reinsert),
  mirroring how `docs/jobs.json` itself is a full snapshot, not an
  incremental log.
- Best-effort: a failed write (bad URL, missing driver, connection error) is
  logged and never fails the run, matching the AI-summary and board-scraper
  failure philosophy elsewhere in this pipeline.
- Skipped whenever `--limit` is set, same as the `docs/jobs.json` write.

The schema is normalized across four tables rather than one flat table —
`company` and `source` are low-cardinality strings repeated on every job, and
a job can list multiple locations, so each gets its own table:

- **`companies`** (`id`, `name` unique, `blurb`) — one row per company;
  `blurb` was previously duplicated onto every one of that company's jobs.
- **`sources`** (`id`, `name` unique) — one row per board type (`workday`,
  `greenhouse`, ...).
- **`jobs`** (`id`, `company_id` FK, `source_id` FK, `title`, `url`,
  `posted_date`, `first_seen`, `description`, `role_summary`, `is_new`) —
  `posted_date` is an absolute `"YYYY-MM-DD"` computed once from
  `first_seen` minus `posted_days` at write time (NULL for date-less boards
  like rippling/bamboohr); the raw `posted_on` display text and the
  relative `posted_days` count are not stored — they'd go stale the moment
  time passes after the write.
- **`job_locations`** (`job_id` FK, `location`, `ordinal`) — one row per
  location a job lists, in original order; location text is stored exactly
  as scraped, with no attempt to dedupe spelling/format variants (e.g.
  "Toronto" vs "Toronto, ON, CAN").

See [`scraper/db.py`](scraper/db.py) for the SQLAlchemy table definitions.

### Setting up each database

No manual schema step is needed for any of these — `write_jobs()` runs
`metadata.create_all(engine)` on every invocation, so the `jobs` table is
created automatically the first time `--database` is used against an empty
database. The steps below just get you a reachable, empty database to point
the URL at.

**SQLite** — no server, no driver install, just a file path:

```bash
python -m scraper.main --database "sqlite:///jobs.db"          # relative path
python -m scraper.main --database "sqlite:////home/me/jobs.db" # absolute path (note 4 slashes)
```

The file is created automatically if it doesn't exist yet — nothing to set
up ahead of time.

**PostgreSQL**:

```bash
pip install psycopg2-binary   # SQLAlchemy's Postgres driver

# Local Postgres via Docker — swap in your own host if you already run one
docker run -d --name jobscraper-pg \
  -e POSTGRES_USER=jobs -e POSTGRES_PASSWORD=jobs -e POSTGRES_DB=jobs \
  -p 5432:5432 postgres:16

# Create the database first if you're not using the one above (Docker's
# POSTGRES_DB already creates it for you):
createdb -h localhost -U jobs jobs

python -m scraper.main --database "postgresql+psycopg2://jobs:jobs@localhost:5432/jobs"
```

**MySQL** (or MariaDB):

```bash
pip install pymysql   # SQLAlchemy's pure-Python MySQL driver

# Local MySQL via Docker — swap in your own host if you already run one
docker run -d --name jobscraper-mysql \
  -e MYSQL_USER=jobs -e MYSQL_PASSWORD=jobs \
  -e MYSQL_DATABASE=jobs -e MYSQL_ROOT_PASSWORD=root \
  -p 3306:3306 mysql:8

python -m scraper.main --database "mysql+pymysql://jobs:jobs@localhost:3306/jobs"
```

In every case, the target database itself (`jobs` in the examples above)
must already exist — SQLAlchemy/the driver can create the `jobs` *table*
inside it, but not the database/schema itself. Only the database server and
an empty database are prerequisites; the table is always handled for you.

## Consuming the data

`docs/jobs.json` is a static, read-only public API — no server, no auth, no
query params, refreshed hourly:

```
GET https://faradumatin.github.io/JobScraper/jobs.json
```

```json
{
  "updated_at": "2026-07-14T15:06:23+00:00",
  "jobs": [ { "...": "..." } ]
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable key, `"{company_slug}:{requisition_id}"` |
| `company` | string | Company display name |
| `title` | string | Job title, as posted |
| `location` | string | Primary location (`locations[0]`) |
| `locations` | string[] | All locations, expanded |
| `url` | string | Direct link to the posting |
| `posted_on` | string | Raw display text, e.g. `"Posted Today"` — not reliably parseable |
| `posted_days` | int \| null | Days since posting; `null` on Rippling/BambooHR, which expose no date |
| `source` | string | Board name (see table above) |
| `first_seen` | string | ISO 8601 timestamp of when this job first appeared in any scrape |
| `is_new` | bool | New since the *previous* run only — flips back to `false` next run |
| `description` | string | Plain-text posting body, HTML stripped, truncated |
| `role_summary` | string | 1-2 sentence AI summary of this posting (blank without an Anthropic key) |
| `company_blurb` | string | 1-2 sentence AI blurb about the company (blank until backfilled) |

**curl**
```bash
curl -s https://faradumatin.github.io/JobScraper/jobs.json | jq '.jobs[] | select(.is_new)'
```

**JavaScript**
```js
const { updated_at, jobs } = await fetch(
  'https://faradumatin.github.io/JobScraper/jobs.json'
).then(r => r.json());

const newJobs = jobs.filter(j => j.is_new);
```

**Python**
```python
import requests

data = requests.get("https://faradumatin.github.io/JobScraper/jobs.json").json()
matches = [j for j in data["jobs"] if "intern" in j["title"].lower()]
```

Full contract, including CORS/versioning notes: [`docs/API.md`](docs/API.md).

## Adding a company or a new board type

**Company already on a supported board** (e.g. Workday) → config only, no
code. Add an entry to `companies` in [`config.json`](config.json) with the
fields listed in the [board table](#supported-job-boards) above, then run:

```bash
python -m scraper.main --company "New Company"
```

to scrape and merge just that company into `docs/jobs.json`, and commit the
result.

**A job board this project doesn't support yet** → add one file in
[`scraper/boards/`](scraper/boards/): subclass `BaseScraper`, implement
`fetch_jobs()` returning normalized `Job` objects, and register the class in
`SCRAPERS` in [`scraper/boards/__init__.py`](scraper/boards/__init__.py).
`scraper/main.py` never imports concrete scrapers directly.

For board-specific gotchas (Workday's pagination cap, date-less boards,
etc.) and the AI-blurb backfill process, see [`CLAUDE.md`](CLAUDE.md).

## Running tests

```bash
python -m pytest                       # run everything
python -m pytest tests/test_workday.py # run one file
```

Every board scraper has its own test file (`tests/test_<board>.py`) plus
coverage for the orchestrator (`test_main.py`), snapshot storage/diffing
(`test_storage.py`), the SQL mirror (`test_db.py`), AI summarization
(`test_summarize.py`), and the blurb backfill script
(`test_backfill_blurbs.py`).

## Dashboard

[`docs/`](docs/) is a vanilla HTML/CSS/JS single-page dashboard over
`jobs.json` — no build step, no framework. To serve it locally:

```bash
python -m http.server 8042 -d docs
```

Then open `http://localhost:8042`. In production it's served directly by
GitHub Pages from the `docs/` folder. Design conventions live in
[`ui_guideline.md`](ui_guideline.md).

## Project layout

```
scraper/
  main.py           # orchestrator: scrape → diff → summarize → save
  models.py         # the Job dataclass, shared by every board scraper
  storage.py        # docs/jobs.json load/diff/save
  db.py             # optional SQL mirror (--database)
  summarize.py      # best-effort Anthropic API calls for summaries/blurbs
  backfill_blurbs.py  # one-time script: generate company blurbs into config.json
  boards/           # one module per job board, registered in __init__.py
config.json         # companies list + reference keyword bank
docs/                # GitHub Pages root: dashboard + generated jobs.json
tests/               # pytest suite, one file per board plus pipeline-level tests
.github/workflows/scrape.yml  # hourly cron that runs the pipeline
```

## Further reading

- [`CLAUDE.md`](CLAUDE.md) — full architecture notes, board-by-board
  gotchas, AI summary/blurb details.
- [`docs/API.md`](docs/API.md) — the complete `jobs.json` API contract.
- [`ui_guideline.md`](ui_guideline.md) — the dashboard's design system.

## License

MIT — see [`LICENSE`](LICENSE).
