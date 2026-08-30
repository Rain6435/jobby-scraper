"""Matches an already-parsed `locations` row (city/region/country_code from
location_resolver.py) against the `towns` gazetteer (scraper/gazetteer.py)
to assign a canonical town_id.

This is a separate concern from location_resolver.py's free-text parsing:
that module turns a raw scraped string into loose structured fields with no
external reference data; this module takes those fields and asks "which
real, gazetteer-known place is this" — an operation that can fail closed
(return None) far more often, since it requires a genuine match against a
fixed, finite list of towns rather than just extracting tokens.

Matching is deliberately tiered and conservative, mirroring
location_resolver.py's own "never guess" contract:

  1. Exact ascii_name + country_code + region-resolved-to-admin1_code.
     Covers the dominant real-world case directly (e.g. "San Francisco,
     California, United States" — city + state + country all agree).
  2. Exact ascii_name + country_code only, when it uniquely identifies one
     town. Multiple gazetteer towns can legitimately share a name within
     one country (there are several "Springfield, US") — in that case this
     tier is ambiguous and intentionally does NOT guess; it falls through
     to tier 3, which will also fail closed for the same input.
  3. Same as 1-2 but matching against each town's short alternate_names
     instead of ascii_name (catches "NYC", "SF", etc. without a hand-
     maintained alias table — see gazetteer.py's alias filtering).
  4. No country_code, or nothing confidently scoped by the above: stop.
     Never attempt an unscoped global name match — "Ontario" with no country
     signal is exactly the ambiguous case (Canadian province vs. a real city
     named Ontario in California) that must resolve to None rather than a
     coin flip.

No fuzzy/edit-distance matching is attempted anywhere in this module. Venue
names ("ProspectLand"), building addresses ("30 Hudson Street"), and
ALL-CAPS tenant codes ("AMER - United States - Nevada - Offsite/Home") are
expected to permanently resolve to None — country_code-based filtering is
the correct fallback for these, not a gap this module should try to close.

A note on None's two causes, for anyone debugging why a specific location
never got a town_id: "no candidate town matched at all" and "multiple
candidates matched, refused to pick one" both return None here. They are
observationally identical from the return value alone; if that distinction
ever needs auditing, add a debug-level log at the ambiguous branches below
rather than changing the return type.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.engine import Connection

from scraper.db import towns_table
from scraper.location_resolver import CA_PROVINCE_TOKENS, US_STATE_TOKENS

# location_resolver.py's region field holds free text ("California", "CA",
# "Ontario", "ON") already confirmed to be a recognized US state or CA
# province token (see parse_location). GeoNames' own admin1_code uses USPS
# 2-letter codes for the US (a direct uppercase of the abbreviation), but
# Canada's admin1_code is instead a two-digit numeric code — confirmed
# against the bundled gazetteer directly (`cities15000.txt`'s CA rows use
# "01".."13", not "AB".."YT"). This table is therefore only needed for
# Canada; the US case is handled by uppercasing the already-recognized
# abbreviation instead of a lookup table.
_CA_PROVINCE_TO_ADMIN1: dict[str, str] = {
    "ab": "01",
    "alberta": "01",
    "bc": "02",
    "british columbia": "02",
    "mb": "03",
    "manitoba": "03",
    "nb": "04",
    "new brunswick": "04",
    "nl": "05",
    "newfoundland and labrador": "05",
    "ns": "07",
    "nova scotia": "07",
    "on": "08",
    "ontario": "08",
    "pe": "09",
    "prince edward island": "09",
    "qc": "10",
    "quebec": "10",
    "sk": "11",
    "saskatchewan": "11",
    "yt": "12",
    "yukon": "12",
    "nt": "13",
    "northwest territories": "13",
    "nu": "06",
    "nunavut": "06",
}

_US_STATE_ABBREVIATIONS: dict[str, str] = {
    token.upper(): token.upper() for token in US_STATE_TOKENS if len(token) == 2
}

# location_resolver.py's US_STATE_TOKENS is a flat set of BOTH forms
# ("california" and "ca") with no pairing between them — region-extraction
# only needs to recognize either form, not translate one into the other.
# GeoNames' admin1_code, however, is always the 2-letter USPS form, so a
# full state name needs an explicit name -> abbreviation table to be usable
# here. This matters more than it might look: confirmed directly against
# production location data that ~1,700 rows use a full state name with no
# accompanying 2-letter code ("Quincy, Massachusetts", not "Quincy, MA") —
# without this table, a city name that's ambiguous within its country (two
# real US towns are named Quincy: IL and MA) can never be disambiguated for
# those rows, since tier 2's country-only match refuses to guess between them.
_US_FULL_NAME_TO_ABBREVIATION: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "dc": "DC",
    "washington dc": "DC",
    "washington d.c.": "DC",
}


def _resolve_admin1_code(region: str, country_code: str) -> str | None:
    """Map a region string already known to be a US-state/CA-province token
    (see location_resolver.py's US_STATE_TOKENS/CA_PROVINCE_TOKENS) to the
    GeoNames admin1_code it corresponds to, scoped by country since the two
    token sets use different code schemes.
    """
    region_lower = region.strip().lower()
    if country_code == "US" and region_lower in US_STATE_TOKENS:
        return _US_STATE_ABBREVIATIONS.get(
            region_lower.upper()
        ) or _US_FULL_NAME_TO_ABBREVIATION.get(region_lower)
    if country_code == "CA" and region_lower in CA_PROVINCE_TOKENS:
        return _CA_PROVINCE_TO_ADMIN1.get(region_lower)
    return None


def _match_towns(
    conn: Connection,
    *,
    name_column: ColumnElement[str],
    name: str,
    country_code: str,
    admin1_code: str | None,
) -> int | None:
    """One scoped lookup against `towns`: exact casefolded match on
    `name_column` + country_code, optionally narrowed further by
    admin1_code. Returns the single matching town's id, or None if zero or
    more than one town matches — ambiguity is refused, never guessed.
    """
    query = select(towns_table.c.id).where(
        towns_table.c.country_code == country_code,
        name_column == name,
    )
    if admin1_code is not None:
        query = query.where(towns_table.c.admin1_code == admin1_code)
    rows = conn.execute(query).fetchall()
    if len(rows) == 1:
        return rows[0].id
    return None


def resolve_town(
    conn: Connection,
    *,
    city: str | None,
    region: str | None,
    country_code: str | None,
) -> int | None:
    """Best-effort match of a parsed location's city/region/country_code
    against the `towns` gazetteer. Returns a town_id on a confident match,
    None otherwise — see module docstring for the tiered matching order and
    why None is a correct, permanent answer for a large share of inputs
    (venue names, tenant codes, ambiguous fragments), not a gap.
    """
    if not city or not country_code:
        return None

    city_casefold = city.strip().casefold()
    admin1_code = _resolve_admin1_code(region, country_code) if region else None

    # Tier 1: exact ascii_name + country + region, when region resolved.
    # ascii_name is compared via func.lower() on both sides (rather than a
    # SQLite-specific COLLATE NOCASE) to keep this portable across the
    # SQLAlchemy backends db.py already supports (sqlite/postgres/mysql).
    if admin1_code is not None:
        town_id = _match_towns(
            conn,
            name_column=func.lower(towns_table.c.ascii_name),
            name=city_casefold,
            country_code=country_code,
            admin1_code=admin1_code,
        )
        if town_id is not None:
            return town_id

    # Tier 2: exact ascii_name + country only, must be unambiguous.
    town_id = _match_towns(
        conn,
        name_column=func.lower(towns_table.c.ascii_name),
        name=city_casefold,
        country_code=country_code,
        admin1_code=None,
    )
    if town_id is not None:
        return town_id

    # Tier 3: alternate_names, same scoping/ambiguity rules. alternate_names
    # is a comma-joined field, not a single name, so this needs a LIKE-based
    # token match rather than an exact-equality one — still scoped by
    # country/admin1 and still refuses ambiguity (>1 candidate -> None).
    like_pattern_variants = [
        f"{city_casefold}",  # sole alias
        f"{city_casefold},%",  # first alias
        f"%,{city_casefold}",  # last alias
        f"%,{city_casefold},%",  # middle alias
    ]
    conditions = [
        func.lower(towns_table.c.alternate_names).like(pattern) for pattern in like_pattern_variants
    ]
    query = select(towns_table.c.id).where(
        towns_table.c.country_code == country_code,
        or_(*conditions),
    )
    if admin1_code is not None:
        query = query.where(towns_table.c.admin1_code == admin1_code)
    rows = conn.execute(query).fetchall()
    if len(rows) == 1:
        return rows[0].id

    return None
