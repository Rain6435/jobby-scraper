---
title: Introduction
description: What Jobby Scraper is, what it produces, and the design rules behind it.
---

Jobby Scraper is a **job pool generator**. It polls the career pages of every company listed in [`config.json`](https://github.com/Rain6435/jobby-scraper/blob/main/config.json) (about 1,290 today), normalizes each posting into a common `Job` shape, and writes the whole set into a SQL database. Other apps read that database and decide which jobs matter to them.

There is no server. It is a Python CLI (`python -m scraper.main`) that you run on a schedule or on demand. In production it is invoked by a separate consumer project, [`job_pipeline`](https://github.com/Rain6435/job_pipeline), which spawns it as a subprocess and then scores the pool for its users.

## What you get

After a run, the database you passed with `--database` holds:

- one row per currently listed posting, with title, URL, full plain-text description, posting date and first-seen timestamp;
- one row per company (with an optional AI-written blurb and a logo path) and per source board;
- every location string a job lists, parsed into city, region, ISO country code and a remote flag, and linked to a canonical [GeoNames](https://www.geonames.org/) town where one matches.

See the [database schema](/jobby-scraper/reference/database-schema/) for the exact tables.

## Design rules

These rules shape almost every decision in the codebase, so they are worth knowing before you change anything.

**The pool is unfiltered.** No keyword, title, location or age filter is applied anywhere in the pipeline. `config.json` still carries a `criteria` block (`keywords` and `blacklist_keywords`), but it is a reference keyword bank for consumers, not something the scraper applies.

**Each write is a full replace.** `--database` holds exactly what the latest run saw, not an accumulating log. A job leaves the pool the first time a fresh scrape of its company no longer lists it (filled, expired or withdrawn). The one exception is a company whose scrape *failed*: its previous jobs are carried forward, because a failure says nothing about whether those postings are still live.

**`Job.id` is the diff key.** Every job is identified by `{company_slug}:{requisition_id}`. It must be stable across runs, otherwise every job looks new, loses its `first_seen` date and is refetched. See [Job identity and diffing](/jobby-scraper/concepts/job-identity-and-diffing/).

**Failures are local.** A board that raises, times out or returns garbage is logged and skipped; the rest of the run continues. The same is true for AI helpers, which return an empty string rather than raising.

**Stay cheap.** Most boards are scraped from a single list endpoint. The few that need a per-posting detail request cache those details between runs so a known posting is never fetched twice.

## Project layout

```
jobby-scraper/
├── config.json              # every company and which board it uses
├── scraper/
│   ├── main.py              # the pipeline / CLI entry point
│   ├── boards/              # one module per job board, registered in __init__.py
│   ├── db.py                # SQLAlchemy schema, load_previous(), write_jobs()
│   ├── models.py            # the Job dataclass
│   ├── location/            # free-text location parsing
│   ├── town_resolver.py     # parsed location -> GeoNames town
│   ├── gazetteer.py         # loads the GeoNames cities1000 dump into `towns`
│   ├── link_parser.py       # parse a single job URL
│   ├── summarize.py         # Anthropic / Ollama helpers
│   ├── logos.py             # SVG logo resolver
│   ├── backfill_blurbs.py   # one-off: AI company blurbs into config.json
│   └── backfill_logos.py    # one-off: logos into data/logos/
├── scripts/                 # discovery tools, CI script, data backfills
├── exploration/             # research notes and probes for custom portals
├── tests/                   # pytest suite with recorded HTTP fixtures
└── docs/                    # this documentation site
```
