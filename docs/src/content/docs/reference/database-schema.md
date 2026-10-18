---
title: Database schema
description: The six tables written to --database, with every column.
---

The schema is defined with SQLAlchemy Core in [`scraper/db.py`](https://github.com/Rain6435/jobby-scraper/blob/main/scraper/db.py) and created automatically on first connection. It is the same on every backend.

```
companies ─┐
           ├──< jobs >──< job_locations >── locations ──> towns
sources ───┘
```

Company names, board names and location strings repeat across thousands of jobs, so each is stored once in a lookup table and referenced by id. A job's locations are a real one-to-many relationship, so they get a join table rather than a JSON column.

## `jobs`

One row per currently listed posting.

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | string, PK | no | `{company_slug}:{requisition_id}`. Stable across runs. |
| `company_id` | int, FK `companies.id` | no | |
| `source_id` | int, FK `sources.id` | no | |
| `title` | string | no | |
| `url` | string | no | Direct link to the posting. |
| `posted_date` | string | yes | `YYYY-MM-DD`. `NULL` for boards without dates; use `first_seen` instead. |
| `first_seen` | string | no | ISO 8601 UTC timestamp of the first run that saw this id. |
| `description` | text | no | Full plain-text description. |
| `role_summary` | text | no | AI summary; empty until filled by an external process. |
| `is_new` | boolean | no | True if this id was not in the database before the latest write. |

## `companies`

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | int, PK | no | |
| `name` | string, unique | no | The config `name` (or, for aggregator boards, the posting's organization). |
| `blurb` | text | no | Short description, empty if none. |
| `group_name` | string | no | Umbrella entity for boards that split one employer into many companies (e.g. `Government of Canada`). Empty otherwise. |
| `logo` | string | no | Relative path to the SVG logo, e.g. `data/logos/cae.svg`. |

## `sources`

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | int, PK | no | |
| `name` | string, unique | no | Board name, e.g. `workday`. |

## `locations`

One row per distinct location string (case and whitespace insensitive).

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | int, PK | no | |
| `name` | string, unique | no | Location text exactly as first scraped. |
| `normalized_key` | string, indexed | yes | `name` with whitespace collapsed and case folded. Decides row identity. |
| `city` | string | yes | Parsed city. |
| `region` | string | yes | Parsed state, province or region. |
| `country_code` | string, indexed | yes | ISO 3166-1 alpha-2. `NULL` when not confidently known. |
| `is_remote` | boolean | no | The text mentions remote work. |
| `town_id` | int, FK `towns.id`, indexed | yes | Matching GeoNames town, or `NULL`. |

See [Locations](/jobby-scraper/concepts/locations/) for how these are derived.

## `job_locations`

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | int, PK | no | |
| `job_id` | string, FK `jobs.id` | no | |
| `location_id` | int, FK `locations.id` | no | |
| `ordinal` | int | no | Position in the job's location list. `0` is the primary location. Unique per job. |

## `towns`

Canonical places from GeoNames `cities1000`. Not filled by a scrape; see [Loading the gazetteer](/jobby-scraper/concepts/locations/#loading-the-gazetteer).

| Column | Type | Null | Description |
| ------ | ---- | ---- | ----------- |
| `id` | int, PK | no | |
| `geoname_id` | int, unique | no | GeoNames' permanent id. |
| `name` | string, indexed | no | Name as GeoNames spells it (may contain non-ASCII). |
| `ascii_name` | string, indexed | no | ASCII spelling, used for matching. |
| `alternate_names` | text | yes | Comma-joined short ASCII aliases, e.g. `NYC`. |
| `country_code` | string, indexed | no | ISO 3166-1 alpha-2. |
| `admin1_code` | string, indexed | yes | First-level region code, unique only within a country. |
| `lat` | float | no | Latitude. |
| `lon` | float | no | Longitude. |
| `population` | int | no | |

## Write semantics

- **Full run:** every row in `job_locations`, `jobs`, `companies`, `sources` and `locations` is deleted and reinserted. `towns` is left alone.
- **Sharded run:** only the shard's companies' `jobs` and `job_locations` rows are replaced. Lookup rows are looked up or inserted, never deleted.
- **`--company` and `--url`:** the snapshot written contains every other company's previous jobs unchanged.

Raw `posted_on` text and the relative `posted_days` are intentionally not stored; only the absolute `posted_date` is.
