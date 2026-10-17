---
title: Job identity and diffing
description: How jobs are identified across runs, how new jobs are detected, and how dates are derived.
---

## The job id

Every job's id is `{company_slug}:{requisition_id}`:

- `company_slug` is the config `name` lowercased with runs of non-alphanumeric characters turned into `-` (`"TD Bank"` becomes `td-bank`). See `slugify()` in `scraper/boards/base.py`.
- `requisition_id` is the board's own identifier for the posting: Greenhouse's job id, Workday's requisition id from `bulletFields`, Ashby's posting UUID, and so on.

The id is the key everything else hangs on, so it has to be identical from one run to the next. If it changes:

- the job looks new and gets a fresh `first_seen`;
- its `posted_date` may be recomputed;
- boards with a detail cache fetch its detail page again;
- consumers lose any state they stored against the old id.

Renaming a company in `config.json` changes the slug and therefore every id for that company.

If a board returns the same id twice in one run (some upstream requisition labels collide), the last one wins at write time and a warning is logged.

## New-job detection

A job is **new** when its id was not in the previous state loaded from the database. New jobs are written with `is_new = true`; everything else gets `false`. This is recomputed on every run, so `is_new` only ever means "new since the last write".

## Removing jobs

There is no explicit delete. Because each write replaces the table contents with the current snapshot, a job disappears the first time a successful scrape of its company does not include it.

A company whose scrape **failed** (exception, or timed out twice) is not treated as having zero jobs. Its previous jobs are carried into the snapshot unchanged, so a transient outage never delists live postings.

## Dates

Three date-related values exist on a job:

| Field | Where it comes from | Stored? |
| ----- | ------------------- | ------- |
| `posted_on` | Raw board text, for example `"Posted 3 Days Ago"`. | No |
| `posted_days` | Days since posting, parsed from the board at scrape time. Relative to now, so it goes stale. | No |
| `first_seen` | UTC timestamp of the first run that saw this id. Carried forward on every later run. | Yes |
| `posted_date` | Absolute `YYYY-MM-DD`, computed once as `first_seen - posted_days`. | Yes |

Once a job has a `posted_date`, it keeps it. `posted_days` only exists on a live scrape, so recomputing the date for a carried-over job would otherwise turn it into `NULL`.

Boards that provide no date (marked in the [boards reference](/jobby-scraper/reference/boards/)) leave `posted_days` as `None`, which leaves `posted_date` as `NULL`. Consumers should use `first_seen` as the age in that case.

Some Workday tenants omit `postedOn` from the list response. For newly seen jobs the scraper then takes the date from the posting's detail page instead.

## The detail cache

Some boards need one extra request per posting to get the description: Workday, Rippling, BambooHR and SmartRecruiters, plus the custom Microsoft, Netflix, EA, Valve, Phenom and GC Jobs scrapers when their detail fetching is enabled. For any id already in the previous state, those boards reuse the stored detail fields instead of requesting the page again. The list request still runs on every scrape, which is how new and removed postings are detected, and list-sourced fields such as the title always come from the current run.

Use `--no-detail-cache` to bypass it for one run. See [Running scrapes](/jobby-scraper/guides/running-scrapes/#re-fetching-cached-descriptions).
