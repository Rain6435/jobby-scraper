"""Free-text job-location string -> structured fields (country, city, region,
remote flag) plus a casing/whitespace-insensitive dedup key.

Split into focused modules (2026-09-19, was one 4,066-line file):
- `location_data.yaml` (repo root: `scraper/location_data.yaml`) — the
  hand-authored lookup tables (COUNTRY_NAMES, LOCATION_ALIASES,
  US_STATE_TOKENS, BARE_CITY_NAME_TO_COUNTRY, ...) as plain data, no
  comments — reviewable/diffable without touching code.
- `data.py` — loads that YAML, restores each table's original Python type,
  and computes derived tables. Explanatory comments (derivation method,
  safety invariants, "how to extend") live here, attached to the loader.
- `regexes.py` — the 56 compiled cleanup/matching patterns.
- `cleaning.py` — `clean_location_for_parsing` and its helpers.
- `resolve.py` — `resolve_country_from_location`.
- `parse.py` — `ParsedLocation` and `parse_location`.
- `export.py` — `export_location_tables`.

Country resolution is a manual Python port of jobby/utils/pipeline/
countryResolver.ts's resolveCountryFromLocation() — same layered matching
order, same "never guess, return None" contract. The *data* tables are no
longer hand-synced between the two: this package is the source of truth,
and `scripts/generate_country_resolver_ts.py` regenerates
jobby/utils/pipeline/generated/country-resolver-data.ts from
`export_location_tables()` below. Only the matching-tier *logic* itself
(the tiered checks in resolve.py/parse.py) is still a separate,
hand-ported implementation in countryResolver.ts — keep that in sync by
hand if the logic changes.

country_code/city/region resolution is best-effort and deliberately
conservative about merging identity: normalized_key only folds whitespace/
case (never merges genuinely different place names), while the country/city/
region fields are additional structured metadata layered on top for
filtering, not used to decide whether two `locations` rows are "the same
place" (see get_or_create_locations in db.py).
"""

from __future__ import annotations

from scraper.location.data import CA_PROVINCE_TOKENS, US_STATE_TOKENS
from scraper.location.export import export_location_tables
from scraper.location.parse import ParsedLocation, parse_location
from scraper.location.resolve import resolve_country_from_location

__all__ = [
    "CA_PROVINCE_TOKENS",
    "ParsedLocation",
    "US_STATE_TOKENS",
    "export_location_tables",
    "parse_location",
    "resolve_country_from_location",
]
