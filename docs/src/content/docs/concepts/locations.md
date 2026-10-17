---
title: Locations
description: How raw location strings become countries, cities, remote flags and GeoNames towns.
---

Boards report locations as free text: `"Toronto, ON"`, `"Remote - Canada"`, `"AMER - United States - Nevada - Offsite/Home"`, `"12 Locations"`. Jobby Scraper keeps that text exactly as scraped and layers structured fields on top.

## Three layers

| Layer | Table | Identity | Purpose |
| ----- | ----- | -------- | ------- |
| Raw string | `locations.name` | The string, with only whitespace and case folded (`normalized_key`) | Display, and a stable id per distinct string. |
| Parsed fields | `locations.city`, `region`, `country_code`, `is_remote` | Not used for identity | Filtering. |
| Canonical town | `towns`, via `locations.town_id` | GeoNames `geoname_id` | Geographic identity, coordinates, population. |

Different spellings of the same place stay separate `locations` rows on purpose: guessing that two strings are the same place and merging them would be impossible to undo. They can still point at the same `towns` row, which is where "same place" is answered.

## Parsing

`parse_location()` in [`scraper/location/`](https://github.com/Rain6435/jobby-scraper/tree/main/scraper/location) runs once per new location string, when it is first inserted:

```python
>>> from scraper.location import parse_location
>>> p = parse_location("Toronto, ON")
>>> p.city, p.region, p.country_code, p.is_remote
('Toronto', 'ON', 'CA', False)
>>> p = parse_location("Remote - Canada")
>>> p.city, p.region, p.country_code, p.is_remote
(None, None, 'CA', True)
>>> p = parse_location("London")
>>> p.city, p.region, p.country_code, p.is_remote
('London', None, None, False)
```

The rules:

- **Never guess.** When the text does not confidently identify a country, `country_code` is `None`. `"London"` alone could be England or Ontario, so it stays unknown.
- The string is first cleaned of ATS noise (store numbers, street addresses, `Hub`/`Office` suffixes, sales-region prefixes, attendance policies), then matched in tiers: country names, ISO alpha-2 and alpha-3 codes, US states, Canadian provinces, known aliases and a table of unambiguous city names.
- `is_remote` is detected from the raw text, so `"Atlanta, GA - Remote"` is remote even though cleaning strips the suffix.
- A company's `default_country` from `config.json` is applied only when the string carries no country signal at all.

The lookup tables live as data in `scraper/location_data.yaml`; the loaders and their comments are in `scraper/location/data.py`. The matching logic is a port of a TypeScript resolver in the consumer project, so changes to the matching tiers should be mirrored there.

## Towns

`resolve_town()` in [`scraper/town_resolver.py`](https://github.com/Rain6435/jobby-scraper/blob/main/scraper/town_resolver.py) matches a parsed location against the `towns` table, again conservatively:

1. City name + country + region (mapped to the GeoNames admin1 code).
2. City name + country, only if exactly one town in that country has that name.
3. The same two checks against each town's short ASCII alternate names (`NYC`, `SF`).
4. Otherwise `None`. There is no fuzzy matching and no global match without a country.

A `NULL` `town_id` is a normal, permanent answer for venue names, addresses and ambiguous fragments. Fall back to `country_code` when filtering.

### Loading the gazetteer

The `towns` table is created automatically but **not filled by a scrape**. It is loaded from GeoNames' `cities1000` dump (every place with a population of at least 1,000, about 171,000 rows), stored at `data/gazetteer/cities1000.txt.gz`:

```python
from scraper.db import get_engine
from scraper.gazetteer import load_towns

engine = get_engine("sqlite:///jobs.db")
with engine.begin() as conn:
    print(load_towns(conn), "towns loaded")
```

`load_towns()` is an idempotent upsert keyed by `geoname_id`, so it is safe to rerun after refreshing the dump. Towns that disappear from a newer dump are kept, since locations may still reference them. Location rows are re-created on every full run, so the next full scrape after loading towns links them.

## Backfills

Country codes are computed once, when a location string is first inserted. A full run re-creates every `locations` row, so parser improvements reach the whole pool on the next full scrape. `scripts/backfill_country_code.py` is a one-off maintenance tool for the consumer project's own `jobscraper_pool` copy of the data, which is not rewritten by a scrape.
