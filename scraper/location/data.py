"""Loads scraper/location_data.yaml — the hand-authored lookup tables that
used to be Python dict/set/frozenset literals directly in this package,
now split out to a plain-data config file so a 1,000+-entry table can be
reviewed/diffed/edited without touching code at all.

Loaded once at import time (module-level, same as when these were literals
— no behavior change, just moved from Python source to a file read).
Table shapes are restored exactly to what the rest of this package expects:
YAML's plain lists become `set[str]` (or `frozenset[str]` for
NON_CITY_PHRASES specifically), and CITY_REGION_COLLISION_TO_COUNTRY's
flattened "city|code" string keys are un-flattened back into
`dict[tuple[str, str], str]`.

Also computes four *derived* tables right after loading — these are
comprehensions over the raw tables above, not authored data, so they stay
as code here rather than moving into the YAML file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DATA_PATH = Path(__file__).resolve().parent.parent / "location_data.yaml"

with DATA_PATH.open(encoding="utf-8") as _f:
    _RAW = yaml.safe_load(_f)

COUNTRY_NAMES: dict[str, str] = _RAW["country_names"]

ALPHA3_TO_ALPHA2: dict[str, str] = _RAW["alpha3_to_alpha2"]

LOCATION_ALIASES: dict[str, str] = _RAW["location_aliases"]

US_STATE_TOKENS: set[str] = set(_RAW["us_state_tokens"])

CA_PROVINCE_TOKENS: set[str] = set(_RAW["ca_province_tokens"])

LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY: set[str] = set(
    _RAW["location_aliases_ambiguous_with_us_ca_city"]
)

NON_CITY_PHRASES: frozenset[str] = frozenset(_RAW["non_city_phrases"])

BARE_CITY_NAME_TO_COUNTRY: dict[str, str] = _RAW["bare_city_name_to_country"]

CITY_REGION_COLLISION_TO_COUNTRY: dict[tuple[str, str], str] = {
    tuple(key.split("|", 1)): value
    for key, value in _RAW["city_region_collision_to_country"].items()
}

# --- Derived tables below: comprehensions over the raw tables above, not
# --- authored data, so these stay as code rather than moving into the
# --- YAML config file. ---

ISO_NAME_TO_CODE: dict[str, str] = {name.lower(): code for code, name in COUNTRY_NAMES.items()}


# Lowercase-keyed alpha-3 -> alpha-2, US/CA only — reuses ALPHA3_TO_ALPHA2
# rather than a new hand-maintained table. Lets parse_location's bare-
# token checks recognize "CAN"/"USA" the same way they already recognize
# "us"/"ca" (BARE_ALPHA2_CODE_TO_COUNTRY) and full names
# (ISO_NAME_TO_CODE) — confirmed live: "CAN, ON, London" left city="CAN"
# unresolved for the same reason "USA, VA, McLean" did before that fix,
# since "can"/"usa" weren't recognized as non-city tokens at all here
# (resolve_country_from_location already handles alpha-3 codes via
# LEADING_ISO3_DASH_RE/TRAILING_ALPHA3_RE, but those are structural,
# position-anchored patterns — not a general bare-token check the way
# BARE_ALPHA2_CODE_TO_COUNTRY is).
ALPHA3_US_CA_TOKENS: dict[str, str] = {
    code.lower(): alpha2 for code, alpha2 in ALPHA3_TO_ALPHA2.items() if alpha2 in ("US", "CA")
}


# Bare, unambiguous ISO alpha-2 country codes ("GB", "FR", "CN", "AU",
# "AM" alone, or "GB,Manchester" with no space after the comma) —
# sampled from live pool data where these simply fell through to None,
# since the only alpha-2 lookups that exist elsewhere in this file
# (US_STATE_TOKENS/CA_PROVINCE_TOKENS, LOCATION_ALIASES' hand-picked
# "us"/"uk") don't cover the other ~240 valid codes at all. Excludes
# every code that collides with a US state or CA province abbreviation
# ("CA", "DE", "IN", "MD", ... — 31 total) so this tier can never
# override the existing, deliberate state/province-wins-ties behavior
# for those; a colliding code still resolves, just via the earlier
# US/CA collision-resolution tier instead of this one, exactly as
# before this table existed. Confirmed the equivalent gap exists in
# jobby/utils/pipeline/countryResolver.ts too (i18n-iso-countries'
# getAlpha2Code resolves names, not codes, verified directly) — both
# files got this tier added together, see that file's own comment.
BARE_ALPHA2_CODE_TO_COUNTRY: dict[str, str] = {
    code.lower(): code
    for code in COUNTRY_NAMES
    if code.lower() not in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
}


US_CA_COUNTRY_COLLISION_CODES = {c.lower() for c in COUNTRY_NAMES} & (
    US_STATE_TOKENS | CA_PROVINCE_TOKENS
)


