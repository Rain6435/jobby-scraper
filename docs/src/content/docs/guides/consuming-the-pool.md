---
title: Consuming the pool
description: How downstream apps should read the job database, with example queries.
---

The database is the scraper's only output. Consumer apps read it directly; there is no API in between. This page covers what you can rely on and some starting queries. The exact columns are in the [database schema](/jobby-scraper/reference/database-schema/).

## What to rely on

- **`jobs.id` is stable** for as long as a posting stays listed: `{company_slug}:{requisition_id}`. Use it as your foreign key when you store per-user state (saved, applied, dismissed) about a job.
- **The pool is a snapshot.** A job missing from the latest run has been delisted. Do not expect old rows to stick around; copy anything you need to keep.
- **Nothing is filtered.** Expect internships next to executive roles, and every country. Apply your own filters.
- **`description` is full plain text**, never truncated. Parse it for skills and requirements.
- **`posted_date` can be `NULL`.** About a dozen boards (Rippling, BambooHR, JazzHR, IBM, Meta, TikTok and others, see the [boards reference](/jobby-scraper/reference/boards/)) do not provide a date. Fall back to `first_seen` for age.
- **Location fields are best-effort.** `country_code`, `city`, `region` and `town_id` are `NULL` whenever the parser was not confident. Treat `NULL` as "unknown", not "no match": include those rows unless you have a reason not to.
- **`role_summary` is usually empty.** The scraper no longer generates it; an external process may fill it in later. See [AI enrichment](/jobby-scraper/concepts/ai-enrichment-and-logos/).

## Reading during a write

A full write deletes and reinserts every row, in a series of short transactions rather than one long one (so readers of other tables in the same SQLite file are not locked out for minutes). The trade-off is that a reader in the middle of a write can briefly see a smaller pool. If that matters, read after the scraper process has exited, or retry when you see an unexpectedly low count.

## Example queries

### Jobs with company and source

```sql
SELECT j.id, j.title, c.name AS company, s.name AS board, j.url,
       COALESCE(j.posted_date, substr(j.first_seen, 1, 10)) AS posted
FROM jobs j
JOIN companies c ON c.id = j.company_id
JOIN sources   s ON s.id = j.source_id
ORDER BY posted DESC;
```

### Jobs in a country, keeping unknown locations

```sql
SELECT DISTINCT j.id, j.title
FROM jobs j
JOIN job_locations jl ON jl.job_id = j.id
JOIN locations l      ON l.id = jl.location_id
WHERE l.country_code = 'CA' OR l.country_code IS NULL;
```

### Remote jobs

```sql
SELECT DISTINCT j.id, j.title, l.name AS location
FROM jobs j
JOIN job_locations jl ON jl.job_id = j.id
JOIN locations l      ON l.id = jl.location_id
WHERE l.is_remote = 1;
```

### Jobs within roughly 50 km of a point

Locations that matched a GeoNames town carry coordinates through `towns`:

```sql
SELECT DISTINCT j.id, j.title, t.name AS town
FROM jobs j
JOIN job_locations jl ON jl.job_id = j.id
JOIN locations l      ON l.id = jl.location_id
JOIN towns t          ON t.id = l.town_id
WHERE t.lat BETWEEN 45.50 - 0.45 AND 45.50 + 0.45
  AND t.lon BETWEEN -73.57 - 0.64 AND -73.57 + 0.64;
```

### Primary location only

`job_locations.ordinal = 0` is the job's primary location:

```sql
SELECT j.id, j.title, l.name AS primary_location
FROM jobs j
JOIN job_locations jl ON jl.job_id = j.id AND jl.ordinal = 0
JOIN locations l      ON l.id = jl.location_id;
```

### New in the latest run

```sql
SELECT id, title FROM jobs WHERE is_new = 1;
```

### Keyword matching

The scraper does not filter, but `config.json` carries a reference keyword bank under `criteria.keywords` and `criteria.blacklist_keywords` (English and French entry-level and early-career terms). You can reuse it in your own matching:

```sql
SELECT id, title FROM jobs
WHERE lower(title) LIKE '%developer%'
  AND lower(title) NOT LIKE '%senior%';
```

## Refreshing one company on demand

An app can ask for a single company's listings to be refreshed without waiting for the next full run:

```bash
python -m scraper.main --company "Acme" --database "<same database URL>"
```

The company name must match `config.json` exactly. All other companies' rows are written back unchanged.
