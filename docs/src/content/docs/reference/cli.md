---
title: CLI reference
description: Every command-line flag for scraper.main and the helper tools.
---

## `python -m scraper.main`

The pipeline. Loads `.env` from the repo root if present.

```bash
python -m scraper.main --database <URL> [options]
python -m scraper.main --company <NAME> --database <URL>
python -m scraper.main --company <NAME> --limit <N> [--verbose]
python -m scraper.main --url <JOB_URL> [--database <URL>]
```

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--database URL` | none | SQLAlchemy URL to read previous state from and write results to, e.g. `sqlite:///jobs.db` or `postgresql+psycopg2://user:pass@host/db`. **Required** unless `--limit` or `--url` is set. |
| `--company NAME` | all | Scrape only this company (exact `name` from `config.json`) and merge its jobs into everyone else's previous jobs. |
| `--limit N` | none | Smoke test: cap the scraped list to N jobs and skip all database reads and writes. |
| `--url URL` | none | Parse one job posting link, print it as JSON, and persist it if `--database` is set. Ignores the other scrape flags. |
| `--verbose` | off | DEBUG logging for every `scraper.*` logger. Same as `LOG_LEVEL=DEBUG`. |
| `--concurrency N` | 16 | Companies scraped in parallel. |
| `--per-company-timeout S` | 120 | Seconds before a slow company gets a fresh attempt queued. `0` or negative disables it. |
| `--shard-size N` | unset | Split a full run into independently written batches of at most N companies. Ignored with `--company`. |
| `--shard-job-target N` | 20000 | With `--shard-size`, the number of jobs each shard is filled up to. |
| `--no-detail-cache` | off | Refetch every posting's detail page this run instead of reusing stored descriptions. |
| `--llm-provider {anthropic,ollama}` | unset | Sets `LLM_PROVIDER` for this process. Has no effect on a scrape, since the scrape makes no AI calls. |

Exit codes: `0` success, `1` failure, `130` interrupted. See [Running scrapes](/jobby-scraper/guides/running-scrapes/#exit-codes).

## `python -m scraper.link_parser`

Parse one job URL. See [Parsing single links](/jobby-scraper/guides/parsing-single-links/).

| Argument | Description |
| -------- | ----------- |
| `URL` (positional) or `--url URL` | The posting to parse. |
| `--database URL` | Also write the job, scoped to its company. |
| `--verbose` | DEBUG logging. |

## `python -m scraper.backfill_blurbs`

Generate AI company blurbs into `config.json` for entries that lack one. Uses `LLM_PROVIDER` to pin a provider.

| Flag | Description |
| ---- | ----------- |
| `--dry-run` | Print what would change; write nothing. |
| `--force` | Regenerate blurbs that already exist. |

## `python -m scraper.backfill_logos`

Resolve SVG logos into `data/logos/` and set `logo` in `config.json`. (`python scripts/backfill_logos.py` is the same tool.)

| Flag | Default | Description |
| ---- | ------- | ----------- |
| `--company NAME` | all | Only this company. |
| `--force` | off | Re-resolve logos that already exist. |
| `--dry-run` | off | Print results; write nothing. |
| `--workers N` | 16 | Concurrent network workers. |

## `python scripts/discover_companies.py`

Find which supported ATS a company uses and optionally add it to `config.json`.

| Flag | Description |
| ---- | ----------- |
| `--company`, `-c NAME` | Company name to probe. Candidate slugs are derived from it. |
| `--slug`, `-s SLUGS` | Comma-separated slugs to try. |
| `--file`, `-f PATH` | File of company names or slugs, one per line. |
| `--board`, `-b BOARDS` | Limit to these boards (comma-separated). |
| `--workday-url URL` | Verify a Workday `wday/cxs` API URL directly. |
| `--workday-base URL` | Its careers base. Derived from `--workday-url` if omitted. |
| `--apply`, `-a` | Append verified companies (with logos) to `config.json`. |
| `--test` | Run the test suite after changing `config.json`. |
| `--workers`, `-w N` | Concurrent probes (default 20). |
| `--json` | Print results as JSON. |

## `python scripts/scout_sp500.py`

Fetch the current S&P 500 list and probe each company's ATS.

| Flag | Description |
| ---- | ----------- |
| `--limit N` | Only scout the first N companies. |
| `--apply`, `-a` | Append verified companies to `config.json`. |
| `--test` | Run CI tests afterwards. |
| `--workers`, `-w N` | Concurrent probes (default 30). |

## `python -m scripts.backfill_companies_logo_column`

Copy `logo` paths from `config.json` into an existing database's `companies.logo` column without running a scrape.

| Flag | Description |
| ---- | ----------- |
| `--database URL` | Database to update. |
| `--dry-run` | Print what would change. |

## `bash scripts/ci.sh`

Run every CI gate locally: tests, `pyright --strict`, the no-`Any` audit, `ruff format --check` and `ruff check`. See [Development](/jobby-scraper/contributing/development/).
