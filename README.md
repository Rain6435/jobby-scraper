# Jobby-Scraper

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Type Checking](https://img.shields.io/badge/pyright-strict-success.svg)](https://github.com/microsoft/pyright)
[![Strict Types](https://img.shields.io/badge/types-zero%20Any-success.svg)](scripts/ci.sh)
[![Linting & Formatting](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Tests](https://img.shields.io/badge/tests-360%2B%20passed-brightgreen.svg)](tests/)

**Jobby-Scraper** is a high-throughput, autonomous multi-platform job aggregation engine. It continuously discovers, scrapes, normalizes, and geocodes job listings from over **1,260+ company career sites across 44+ applicant tracking systems (ATS) and custom enterprise career portals**, persisting them into a normalized relational SQL database pool.

---

## Core Philosophy

- **Unfiltered Pool Generation**: Every currently-listed posting from every configured company is scraped and stored without keyword, title, location, or age curation. Downstream consumer applications (such as [`job_pipeline`](https://github.com/Rain6435/job_pipeline)) query and filter this raw pool for custom matching, scoring, and user recommendations.
- **Full-Replace Sync Semantics**: A job posting remains in the pool as long as fresh scrapes return it. Once a company removes a listing (filled, expired, or closed), it is dropped from the active pool. The database is a full-replace snapshot of current market reality, not an unbounded accumulating log.
- **Differential Scraping & Caching**: Postings are tracked via stable IDs (`{company_slug}:{requisition_id}`). Detail-fetch caching avoids redundant HTTP requests for heavy boards while picking up fresh listings immediately.
- **Relational SQL Sink**: The pipeline persists to any SQLAlchemy-compatible database (SQLite, PostgreSQL, MySQL) with normalized tables for companies, sources, jobs, locations, and GeoNames-backed canonical towns.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Input ["Configuration & Seed Data"]
        Config["config.json\n(1,260+ companies across 44+ platforms)"]
        Gazetteer["data/gazetteer/cities15000.txt.gz\n(GeoNames Cities Database)"]
    end

    subgraph ScraperEngine ["Scraper Engine (scraper/main.py)"]
        WorkerPool["ThreadPoolExecutor\n(--concurrency N, default 16)"]
        BoardScrapers["44+ Board Scrapers\n(Workday, Greenhouse, Ashby, Lever, etc.)"]
        RetrySession["HTTPAdapter + urllib3.Retry\n(Exponential backoff, 429/5xx retry)"]
        DiffEngine["Diff Engine & Detail Cache\n(BaseScraper._cached_detail)"]
    end

    subgraph Resolvers ["Resolution & Enrichment"]
        LocResolver["Location Resolver\n(ISO alpha-2 country, region, city, remote flag)"]
        TownResolver["Town Resolver\n(GeoNames geoname_id, lat, lon, population)"]
        AIBlurbs["Company Blurbs & Summarizer\n(Anthropic / Ollama Cloud Key Rotation)"]
    end

    subgraph DatabaseSink ["Relational Database Sink (--database)"]
        DB[(SQLAlchemy Engine:\nPostgreSQL / SQLite / MySQL)]
        T_Companies["companies"]
        T_Sources["sources"]
        T_Jobs["jobs"]
        T_Locations["locations"]
        T_JobLocs["job_locations"]
        T_Towns["towns"]
    end

    subgraph Downstream ["Consumers"]
        ConsumerApp["job_pipeline Daemon\n(Downstream Matching & Scoring)"]
    end

    Config --> WorkerPool
    WorkerPool --> BoardScrapers
    BoardScrapers --> RetrySession
    RetrySession --> DiffEngine
    DiffEngine --> LocResolver
    Gazetteer --> TownResolver
    LocResolver --> TownResolver
    TownResolver --> DB
    AIBlurbs -.-> DB
    DB --> T_Companies & T_Sources & T_Jobs & T_Locations & T_JobLocs & T_Towns
    DB --> ConsumerApp
```

---

## Database Schema

The database sink uses SQLAlchemy with a normalized schema across 6 tables:

```mermaid
erDiagram
    companies ||--o{ jobs : "offers"
    sources ||--o{ jobs : "scraped_from"
    jobs ||--o{ job_locations : "located_at"
    locations ||--o{ job_locations : "joined_in"
    towns ||--o{ locations : "resolves_to"

    companies {
        int id PK
        string name UK "Company display name"
        text blurb "Short company overview"
        string group_name "Umbrella entity group (e.g. Government of Canada)"
    }

    sources {
        int id PK
        string name UK "Board identifier (e.g. workday, greenhouse)"
    }

    jobs {
        string id PK "Diff key: {company_slug}:{requisition_id}"
        int company_id FK
        int source_id FK
        string title "Normalized job title"
        string url "Direct link to posting"
        string posted_date "Derived absolute date (YYYY-MM-DD)"
        string first_seen "ISO 8601 discovery timestamp"
        text description "Full plain-text description"
        text role_summary "AI-generated summary"
        boolean is_new "New in current scrape run"
    }

    locations {
        int id PK
        string name UK "Raw location string exactly as scraped"
        string normalized_key "Whitespace/case folded key"
        string city "Parsed city name"
        string region "Parsed state/province"
        string country_code "ISO 3166-1 alpha-2 code"
        boolean is_remote "Remote position flag"
        int town_id FK "Reference to canonical GeoNames town"
    }

    job_locations {
        int id PK
        string job_id FK
        int location_id FK
        int ordinal "Location index (0 = primary)"
    }

    towns {
        int id PK
        int geoname_id UK "GeoNames permanent identifier"
        string name "Town name"
        string ascii_name "ASCII representation"
        text alternate_names "Aliases and abbreviations"
        string country_code "ISO 3166-1 alpha-2"
        string admin1_code "State/Province code"
        float lat "Latitude"
        float lon "Longitude"
        int population "Census population"
    }
```

---

## Supported Job Boards (44+)

| Platform / Source | Board Identifier | Key Config Parameters | Dates Available? | Caches Details? |
| :--- | :--- | :--- | :---: | :---: |
| **Workday** | `workday` | `url`, `careers_base` | Yes (`postedOn`) | Yes |
| **Greenhouse** | `greenhouse` | `token` | Yes (`first_published`) | List-only |
| **Ashby** | `ashby` | `slug` | Yes (`publishedAt`) | List-only |
| **Lever** | `lever` | `company` (slug) | Yes (`createdAt`) | List-only |
| **BambooHR** | `bamboohr` | `company` (subdomain) | Fallback (`first_seen`) | Yes |
| **SmartRecruiters** | `smartrecruiters` | `company` (identifier) | Yes (`releasedDate`) | Yes |
| **Rippling** | `rippling` | `board_id` | Fallback (`first_seen`) | Yes |
| **Workable** | `workable` | `company` (slug) | Yes (`published_on`) | List-only |
| **Recruitee** | `recruitee` | `company` (subdomain) | Yes (`published_at`) | List-only |
| **Breezy HR** | `breezy` | `company` (subdomain) | Yes (`published_date`) | List-only |
| **Personio** | `personio` | `company` (subdomain) | Yes (`createdAt` XML) | List-only |
| **Teamtailor** | `teamtailor` | `company` (subdomain) | Yes (`date_published`) | List-only |
| **Pinpoint** | `pinpoint` | `company` (subdomain) | Yes (`created_at`) | List-only |
| **Jobvite** | `jobvite` | `company_id` (companyEId) | Yes (`date` XML) | List-only |
| **JazzHR** | `jazzhr` | `company` (subdomain) | Fallback (`first_seen`) | List-only |
| **Oracle Cloud CX** | `oraclecloud` | `tenant`, `site_number` | Yes (`PostedDate`) | List-only |
| **SAP SuccessFactors**| `successfactors` | `company`, `domain` | Yes (`pubDate` RSS) | List-only |
| **ADP** | `adp` | `cid`, `cc_id` | Yes (`postDate`) | List-only |
| **Paylocity** | `paylocity` | `guid` | Yes (`postedDate`) | List-only |
| **iCIMS** | `icims` | `tenant`, `domain` | Yes (`Posted Date`) | List-only |
| **Phenom TXP** | `phenom` | `url`, `max_pages` | Yes (`postedDate`) | List-only |
| **Jibe** | `jibe` | `tenant` or `url` | Yes (`create_date`) | List-only |
| **Amazon** | `amazon` | `category`, `country` | Yes | List-only |
| **Apple** | `apple` | `search`, `location` | Yes | List-only |
| **Google** | `google` | `query`, `location` | Yes | List-only |
| **Microsoft** | `microsoft` | `query`, `location` | Yes | List-only |
| **Meta** | `meta` | `query` | Yes | List-only |
| **Netflix** | `netflix` | `query`, `location` | Yes | List-only |
| **Atlassian** | `atlassian` | `category`, `location` | Yes (`updatedDate`) | List-only |
| **Shopify** | `shopify` | `location`, `keyword` | Yes | Yes |
| **IBM** | `ibm` | N/A | Yes | List-only |
| **Electronic Arts** | `ea` | `search`, `max_pages` | Yes | List-only |
| **Valve** | `valve` | N/A | Fallback | List-only |
| **Jane Street** | `janestreet` | `location` | Fallback | List-only |
| **TikTok** | `tiktok` | `keyword`, `max_pages` | Yes | List-only |
| **GovernmentJobs** | `governmentjobs` | `agency` (slug) | Yes (`pubDate` RSS) | List-only |
| **USAJobs** | `usajobs` | API Key in `.env` | Yes | List-only |
| **ReliefWeb** | `reliefweb` | N/A | Yes (`date.created`) | List-only |
| **GC Jobs (Canada)**| `gc_jobs` | `department`, `location` | Yes | List-only |
| **Québec Emploi** | `quebec_emploi` | `region`, `query` | Yes | List-only |
| **Bloomberg / Avature**| `bloomberg` | `url`, `query` | Yes | List-only |
| **Climatebase** | `climatebase` | `keywords` | Yes | List-only |
| **CMA Heritage** | `cma_heritage` | N/A | Yes | List-only |
| **CIP Planning** | `cip_planning` | N/A | Yes | List-only |
| **IDC Career Centre**| `idc_career_centre` | N/A | Yes | List-only |

---

## Installation & Setup

### Prerequisites
- **Python 3.12+**
- Virtual environment manager (`venv` or `uv`)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Rain6435/jobby-scraper.git
cd jobby-scraper

# Using standard venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (.env)
Copy [.env.example](.env.example) to `.env` and supply optional credentials:

```bash
cp .env.example .env
```

| Variable | Description | Default / Requirement |
| :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key for company blurbs (`scraper.backfill_blurbs`) | Optional |
| `ANTHROPIC_AUTH_TOKEN`| Claude Code OAuth token (alternative to API key) | Optional |
| `OLLAMA_API_KEY` | Ollama Cloud API key(s). Supports comma-separated keys for auto-rotation | Optional |
| `LLM_PROVIDER` | Pin AI provider: `anthropic` or `ollama` | Optional (`auto` fallback) |
| `USAJOBS_API_KEY` | Key from developer.usajobs.gov (needed only for `usajobs` board) | Optional |
| `USAJOBS_USER_AGENT` | Registered email for USAJobs API access | Optional |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

---

## CLI Usage

### 1. Full Production Scrape
Runs all configured companies, diffs against existing database state, and performs a full-replace write:

```bash
# SQLite
python -m scraper.main --database "sqlite:///jobs.db"

# PostgreSQL (ensure psycopg2 is installed)
python -m scraper.main --database "postgresql+psycopg2://user:password@localhost:5432/jobs"
```

### 2. On-Demand Single Company Refresh
Refreshes a single company's jobs and merges them into the existing database pool:

```bash
python -m scraper.main --company "Stripe" --database "sqlite:///jobs.db"
```

### 3. Smoke Test (No Database Writes)
Scrapes a single job or company with debug logging, skipping database writes entirely:

```bash
python -m scraper.main --company "Figma" --limit 1 --verbose
```

### 4. Concurrency, Sharding & Timeout Tuning
Control parallel execution, memory limits, and straggler resilience:

```bash
# Scrape 32 companies concurrently, split into 100-company database transaction shards
python -m scraper.main \
  --database "sqlite:///jobs.db" \
  --concurrency 32 \
  --shard-size 100 \
  --per-company-timeout 90
```

- `--concurrency N` (default `16`): Parallel worker threads.
- `--shard-size N` (default unset/all): Splits run into independent shards to bound memory and isolate database transactions.
- `--per-company-timeout N` (default `120s`): Abandons and requeues slow stragglers so the thread pool does not stall.
- `--no-detail-cache`: Forces detail pages to re-fetch even if the job ID is already known.

### 5. Company Blurb Backfill
Generates or updates 1-2 sentence AI company overviews in `config.json`:

```bash
python -m scraper.backfill_blurbs
```

---

## Adding Companies & Discovery

### Autonomous Company Discovery
Use the built-in probing utility to find which ATS a company uses and auto-verify it:

```bash
# Probe across Greenhouse, Ashby, Lever, Workday, BambooHR, SmartRecruiters, etc.
python scripts/discover_companies.py --query "Databricks" --probe
```

### S&P 500 Multi-ATS Scout
Automated scanner for large multinationals:

```bash
python scripts/scout_sp500.py --sector "Information Technology" --limit 20
```

### Manual Configuration
Add an entry to `companies` in [config.json](config.json):

```json
{
  "name": "Anthropic",
  "board": "lever",
  "company": "anthropic",
  "blurb": "Anthropic is an AI safety and research company building reliable, interpretable steering systems."
}
```

For **Workday**, inspect the company's careers portal via browser DevTools (Network tab -> XHR -> filter for `jobs`):
```json
{
  "name": "Salesforce",
  "board": "workday",
  "url": "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs",
  "careers_base": "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site"
}
```

---

## Developing New Scrapers

All scrapers inherit from `BaseScraper` in `scraper/boards/base.py`.

```python
from scraper.boards.base import BaseScraper
from scraper.models import Job


class CustomScraper(BaseScraper):
    source = "custom"

    def fetch_jobs(self) -> list[Job]:
        # self.session provides built-in exponential backoff and retry
        resp = self.session.get("https://api.example.com/jobs", timeout=15)
        resp.raise_for_status()

        jobs: list[Job] = []
        for item in resp.json()["data"]:
            jobs.append(
                Job(
                    id=f"{self.slug}:{item['id']}",
                    company=self.name,
                    title=item["title"],
                    location=item["location"],
                    url=item["apply_url"],
                    posted_on=item["posted_at"],
                    source=self.source,
                )
            )
        return jobs
```

Register the new scraper class in `SCRAPERS` in `scraper/boards/__init__.py` and define its TypedDict config in `scraper/config_types.py`.

---

## Code Quality & Engineering Standards

This repository maintains rigorous quality gates enforced via CI:

- **Strict Type Checking**: Pyright in strict mode (`pyright --strict`).
- **Zero `Any` Policy**: CI runs an automated audit verifying zero occurrences of `Any` in `scraper` and `tests`.
- **Zero Suppression Comments**: No `type: ignore` or `pyright: ignore` comments are allowed.
- **Ruff Linting & Formatting**: Strict linting rules (`E`, `F`, `I`, `UP`) and 100-char line limit.
- **Comprehensive Test Suite**: Over 360+ tests with mock HTTP fixtures (`responses`).

To run all quality gates locally:
```bash
bash scripts/ci.sh
```

To run tests only:
```bash
pytest -n auto
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
