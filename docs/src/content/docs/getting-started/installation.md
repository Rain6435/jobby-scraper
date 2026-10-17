---
title: Installation
description: Install Jobby Scraper and its optional database drivers and API keys.
---

## Requirements

- **Python 3.12 or newer.** The code uses 3.12 syntax and CI runs on 3.12.
- A SQL database. SQLite works out of the box; anything else SQLAlchemy supports works with its driver installed.

## Install

```bash
git clone https://github.com/Rain6435/jobby-scraper.git
cd jobby-scraper

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` installs both the runtime dependencies (`requests`, `sqlalchemy`, `anthropic`, `python-dotenv`, `pyyaml`) and the development tools (`pytest`, `pytest-xdist`, `responses`, `pyright`, `ruff`, `beautifulsoup4`).

### Database drivers

Only SQLite's driver ships with Python. For other databases install the driver your SQLAlchemy URL names:

| Database   | Example URL                                         | Driver package     |
| ---------- | --------------------------------------------------- | ------------------ |
| SQLite     | `sqlite:///jobs.db`                                 | none               |
| PostgreSQL | `postgresql+psycopg2://user:pass@host:5432/jobs`    | `psycopg2-binary`  |
| MySQL      | `mysql+pymysql://user:pass@host/jobs`               | `pymysql`          |

## Environment variables

Everything is optional. Copy the example file and fill in only what you need:

```bash
cp .env.example .env
```

`scraper.main` and `scraper.backfill_blurbs` load `.env` from the repo root automatically.

- **No keys at all:** scraping, descriptions and the database all work. AI company blurbs stay empty.
- **`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `OLLAMA_API_KEY`:** only needed to generate company blurbs with `python -m scraper.backfill_blurbs`.
- **`USAJOBS_API_KEY` and `USAJOBS_USER_AGENT`:** only needed for the `usajobs` board. Without them that board logs a warning and contributes zero jobs.

The full list is in [Environment variables](/jobby-scraper/reference/environment-variables/).

## The `data` directory

`data/` in the repository is a symlink to `../data`. In production this repo is checked out inside the parent `job_pipeline` project and shares that project's data folder, which holds the logos (`data/logos/`), the GeoNames dump (`data/gazetteer/cities1000.txt.gz`) and the Ollama key-rotation state. If you run the scraper standalone, create a `data` folder next to the repo (or replace the symlink) before running the logo tools.

## Check the install

```bash
python -m pytest -q
```

Tests use recorded HTTP fixtures, so they need no network access.
