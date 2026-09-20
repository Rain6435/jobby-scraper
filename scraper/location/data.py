"""Loads scraper/location_data.yaml — the hand-authored lookup tables that
used to be Python dict/set/frozenset literals directly in this package,
now split out to a plain-data config file so a 1,000+-entry table can be
reviewed/diffed/edited without touching code at all.

Loaded once at import time (module-level, same as when these were literals
— no behavior change, just moved from Python source to a file read).
Table shapes are restored exactly to what the rest of this package expects:
YAML's plain lists become `set[str]` (or `frozenset[str]` for
NON_CITY_PHRASES specifically — see that assignment below), and
CITY_REGION_COLLISION_TO_COUNTRY's flattened "city|code" string keys are
un-flattened back into `dict[tuple[str, str], str]`.

Also computes four *derived* tables right after loading — these are
comprehensions over the raw tables above, not authored data, so they stay
as code here rather than moving into the YAML file. TS independently
re-derives its own equivalents the same way from its own copy of
COUNTRY_NAMES/US_STATE_TOKENS/CA_PROVINCE_TOKENS (see
jobby/utils/pipeline/countryResolver.ts), so these four never need
generating into the TS side either — see export.py's own docstring.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_DATA_PATH = Path(__file__).resolve().parent.parent / "location_data.yaml"

with _DATA_PATH.open(encoding="utf-8") as _f:
    _RAW = yaml.safe_load(_f)

# Mirrors jobby/shared/countryResolver.ts's COUNTRY_NAMES (alpha-2 -> display
# name).
COUNTRY_NAMES: dict[str, str] = _RAW["country_names"]

# ISO 3166-1 alpha-3 -> alpha-2, restricted to codes COUNTRY_NAMES actually
# has a name for (generated from i18n-iso-countries' getAlpha3Codes(), the
# same package jobby/utils/pipeline/countryResolver.ts already depends on,
# filtered to this file's own alpha-2 set — not hand-typed, to avoid a typo
# silently mismapping a country). Several ATS vendors' location feeds lead
# with an alpha-3 code instead of alpha-2 — e.g. "BRA - Sao Paulo - Sao
# Paulo (Torre Z)" or "CAN-ON-Kitchener" — which nothing else here
# recognizes without this table.
ALPHA3_TO_ALPHA2: dict[str, str] = _RAW["alpha3_to_alpha2"]

# Mirrors countryResolver.ts's LOCATION_ALIASES exactly.
LOCATION_ALIASES: dict[str, str] = _RAW["location_aliases"]

# Mirrors countryResolver.ts's US_STATE_TOKENS exactly.
US_STATE_TOKENS: set[str] = set(_RAW["us_state_tokens"])

CA_PROVINCE_TOKENS: set[str] = set(_RAW["ca_province_tokens"])

# The subset of LOCATION_ALIASES keys that are ALSO real US/CA town names
# ("England, AR", "Scotland, SD", "Wales, WI", "Holland, MI", "New York
# City" itself) — verified against the bundled GeoNames gazetteer (single-
# country, US/CA-only match for each). Every other LOCATION_ALIASES key
# ("usa", "us", "uk", "korea", "britain", ...) is never a real place name
# anywhere. Used to withhold the LOCATION_ALIASES token match when a real
# US/CA state/province token is present elsewhere in the string —
# confirmed live: "Holland, MI" was resolving to "NL" via the alias match
# before the US/CA collision tier ever got a chance to see "MI". Mirrors
# jobby/utils/pipeline/countryResolver.ts's
# LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY — keep both in sync.
LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY: set[str] = set(
    _RAW["location_aliases_ambiguous_with_us_ca_city"]
)

# Work-mode/venue phrases that show up as the trailing token in a
# "<CountryAlias>, <ST>, <phrase>" or "<ST>, <phrase>" shape but are never
# a real city name ("USA, ID, Home Office", "USA, IA, Remote", "Utah,
# Work at Home" after leading-word-remote-suffix comma insertion) —
# sampled from live pool data. Deliberately small and hand-curated rather
# than a broad heuristic — this only excludes the specific phrases
# confirmed live, not a guess at what "sounds like" a venue. Note: a
# `frozenset`, not a plain `set` — the one exception among this module's
# list-shaped tables, preserved exactly from the pre-YAML-extraction type.
NON_CITY_PHRASES: frozenset[str] = frozenset(_RAW["non_city_phrases"])

# Lowest-priority fallback: a location that is nothing but a bare city name
# ("Montreal", "Toronto", "Mumbai") with no country/province/ISO signal at
# all in the string. Derived from GeoNames' cities1000 dump: grouped every
# gazetteer row by lowercased ascii_name, kept only names that map to
# EXACTLY ONE country_code across the full worldwide dataset — no
# population-based tie-breaking (a spot check showed that gets real cases
# wrong even for "obviously safe" names). Ties are excluded entirely
# rather than guessed, preserving this package's "never guess" contract.
# Further filtered to city names actually observed in scraped job
# locations, then hand-reviewed to drop known false positives ("apac" is a
# real Ugandan town but in job postings this string is virtually always
# the Asia-Pacific acronym; "federal" is a real Argentine town but too
# generic/administrative a word to trust bare). To add more entries later,
# re-run the same derivation against newly observed unresolved locations
# rather than hand-typing a new city — hand-typing skips the single-
# country-match safety check every existing entry passed.
BARE_CITY_NAME_TO_COUNTRY: dict[str, str] = _RAW["bare_city_name_to_country"]

# Sub-national region names (states, provinces, counties) for countries
# outside US and Canada where "<City>, <Region>" or bare "<Region>" is
# observed in job locations without an explicit country suffix (e.g.
# "Guadalajara, Jalisco", "Hangzhou, Zhejiang", "Munich, Bavaria", "High
# Wycombe, Buckinghamshire", "Cohuna, VIC", "Pindamonhangaba, São Paulo").
# Verified to have zero collisions with US_STATE_TOKENS,
# CA_PROVINCE_TOKENS, or LOCATION_ALIASES.
SUB_NATIONAL_REGION_TO_COUNTRY: dict[str, str] = _RAW["sub_national_region_to_country"]

# (city.casefold(), collision_code.lower()) -> the real country, for cities
# whose parsed region happens to be a US-state/CA-province abbreviation
# that ALSO collides with a different country's ISO code ("Bangalore, IN"
# resolves region="IN" correctly as a US-state-shaped token, but IN here
# means India, not Indiana). Derived the same way as
# BARE_CITY_NAME_TO_COUNTRY (see that table's comment for the full
# method), covering BOTH US-collision codes like "in"/"de" resolved as
# country_code="US", and CA-province-collision codes like "pe"/"nl"/"sk"
# resolved as country_code="CA" — e.g. "Lima, PE" was misresolving to
# Canada via Prince Edward Island's "pe" before that second derivation
# pass covered it. Kept only when (a) no real town named `city` exists in
# the US OR CA jurisdiction the collision_code would otherwise mean, and
# (b) exactly one gazetteer town named `city` exists in the collided-with
# country (never a tie, same "never guess" contract as every other table
# here). Un-flattened from the on-disk "city|code" string key (the same
# shape jobby/utils/pipeline/countryResolver.ts's own copy of this table
# already uses, kept identical so the TS generator needs zero shape
# translation). Re-run the same derivation against fresh unresolved-
# location data to add more entries — do not hand-type new ones, for the
# same safety-check reason BARE_CITY_NAME_TO_COUNTRY's own comment gives.
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
# _LEADING_ISO3_DASH_RE/TRAILING_ALPHA3_RE, but those are structural,
# position-anchored patterns — not a general bare-token check the way
# BARE_ALPHA2_CODE_TO_COUNTRY is).
ALPHA3_US_CA_TOKENS: dict[str, str] = {
    code.lower(): alpha2 for code, alpha2 in ALPHA3_TO_ALPHA2.items() if alpha2 in ("US", "CA")
}

# Bare, unambiguous ISO alpha-2 country codes ("GB", "FR", "CN", "AU",
# "AM" alone, or "GB,Manchester" with no space after the comma) —
# sampled from live pool data where these simply fell through to None,
# since the only alpha-2 lookups that exist elsewhere in this package
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
