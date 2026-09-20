"""export_location_tables(): re-shapes this package's hand-authored data
tables into plain JSON-serializable data, consumed by
scripts/generate_country_resolver_ts.py to regenerate
jobby/utils/pipeline/generated/country-resolver-data.ts.
"""

from __future__ import annotations

from scraper.location.data import (
    BARE_CITY_NAME_TO_COUNTRY,
    CA_PROVINCE_TOKENS,
    CITY_REGION_COLLISION_TO_COUNTRY,
    COUNTRY_NAMES,
    LOCATION_ALIASES,
    LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY,
    NON_CITY_PHRASES,
    SUB_NATIONAL_REGION_TO_COUNTRY,
    US_STATE_TOKENS,
)


def export_location_tables() -> dict[str, object]:
    """Hand-authored lookup tables, as plain JSON-serializable data.

    Used by scripts/generate_country_resolver_ts.py to regenerate
    jobby/utils/pipeline/generated/country-resolver-data.ts — the TS
    resolver's only source for these tables, so the two can't drift the
    way they did repeatedly by hand (e.g. a fix landing in
    CITY_REGION_COLLISION_TO_COUNTRY here and being missed in
    countryResolver.ts's hand-typed copy).

    Only the hand-authored tables are exported. Several other tables in
    this file (ISO_NAME_TO_CODE, ALPHA3_US_CA_TOKENS,
    US_CA_COUNTRY_COLLISION_CODES, BARE_ALPHA2_CODE_TO_COUNTRY) are
    derived from these at import time via comprehensions — TS
    independently re-derives its own equivalents the same way from its
    copy of COUNTRY_NAMES/US_STATE_TOKENS/CA_PROVINCE_TOKENS, so they
    don't need generating separately.

    The matching-tier *logic* (resolve_country_from_location's tiered
    checks, parse_location's city/region extraction) is NOT exported —
    only the data. TS's own implementation of that logic is still a
    separate, hand-ported file; keep it in sync by hand as before.
    """
    return {
        "country_names": COUNTRY_NAMES,
        "location_aliases": LOCATION_ALIASES,
        "location_aliases_ambiguous_with_us_ca_city": sorted(
            LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY
        ),
        "us_state_tokens": sorted(US_STATE_TOKENS),
        "ca_province_tokens": sorted(CA_PROVINCE_TOKENS),
        "non_city_phrases": sorted(NON_CITY_PHRASES),
        "bare_city_name_to_country": BARE_CITY_NAME_TO_COUNTRY,
        "sub_national_region_to_country": SUB_NATIONAL_REGION_TO_COUNTRY,
        # Tuple keys aren't JSON-safe — flatten to the same "city|code"
        # string key countryResolver.ts already hand-typed its own copy
        # with, so the generated TS table needs zero shape translation
        # at the call site.
        "city_region_collision_to_country": {
            f"{city}|{code}": country
            for (city, code), country in CITY_REGION_COLLISION_TO_COUNTRY.items()
        },
    }
