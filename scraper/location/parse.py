"""Structural parse of a raw scraped location string into ParsedLocation
(country_code/city/region/is_remote), plus the normalized_key used for row
identity — see get_or_create_locations in db.py for why normalized_key is
kept deliberately separate from (and never influenced by) the best-effort
country/city/region extraction.
"""

from __future__ import annotations

import functools
import unicodedata
from dataclasses import dataclass

from scraper.location.cleaning import clean_location_for_parsing
from scraper.location.data import (
    ALPHA3_TO_ALPHA2,
    ALPHA3_US_CA_TOKENS,
    BARE_ALPHA2_CODE_TO_COUNTRY,
    CA_PROVINCE_TOKENS,
    CITY_REGION_COLLISION_TO_COUNTRY,
    ISO_NAME_TO_CODE,
    LOCATION_ALIASES,
    LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY,
    NON_CITY_PHRASES,
    US_STATE_TOKENS,
)
from scraper.location.regexes import PAREN_RE, REMOTE_KEYWORD_RE, VENUE_PREFIX_RE, WHITESPACE_RE
from scraper.location.resolve import resolve_country_from_location


def _normalize_key(raw: str) -> str:
    """Trim + casefold + collapse whitespace — the only transformation ever
    used to decide "is this the same locations row as an existing one."
    Deliberately does NOT expand abbreviations or reorder tokens: that's
    exactly the kind of guess that could silently merge two different real
    places, which get_or_create_locations must never do at the identity
    level (see its docstring in db.py). Abbreviation/alias folding only
    happens for the separately-stored country_code/city/region fields below.
    """
    return WHITESPACE_RE.sub(" ", raw.strip()).casefold()


@dataclass(frozen=True)
class ParsedLocation:
    raw: str
    normalized_key: str
    city: str | None
    region: str | None
    country_code: str | None
    is_remote: bool


@functools.lru_cache(maxsize=16384)
def parse_location(raw: str) -> ParsedLocation:
    """Best-effort structural parse of a raw scraped location string. Only
    `normalized_key` feeds row identity (see get_or_create_locations);
    city/region/country_code/is_remote are additive metadata for filtering,
    not used to decide whether two rows represent the same place.
    """
    # normalized_key (row identity — see get_or_create_locations) is always
    # derived from the untouched raw string, never the cleaned one: cleaning
    # is a best-effort aid to country/city/region/is_remote extraction only,
    # and must never change which `locations` row a given raw string maps
    # to, or two differently-formatted scrapes of the same posting could
    # silently dedup into two rows (or vice versa) depending on which one
    # a future cleaning-pattern tweak happens to match.
    normalized_key = _normalize_key(raw)
    cleaned = clean_location_for_parsing(raw)
    # Checked against raw, not cleaned: cleanup steps exist to strip noise
    # for city/region/country extraction, and at least one of them (the
    # trailing "<ST> - <suffix>" strip) can legitimately discard a
    # trailing remote-keyword suffix ("Atlanta, GA - Remote") as part of
    # normal operation. raw can only ever contain MORE signal than
    # cleaned, never less, so this is strictly safer than checking
    # cleaned — no existing cleanup step removes a "remote" mention that
    # wasn't itself noise.
    is_remote = bool(REMOTE_KEYWORD_RE.search(raw))
    country_code = resolve_country_from_location(cleaned)

    without_parens = PAREN_RE.sub(" ", cleaned).strip()
    tokens = [t.strip() for t in without_parens.split(",") if t.strip()]

    city: str | None = None
    region: str | None = None
    if tokens:
        first = tokens[0]
        first_lower = first.lower()
        first_upper = first.upper()
        is_recognized_non_city = (
            first_lower in US_STATE_TOKENS
            or first_lower in CA_PROVINCE_TOKENS
            or first_lower in LOCATION_ALIASES
            or first_lower in ISO_NAME_TO_CODE
            or first_lower in BARE_ALPHA2_CODE_TO_COUNTRY
            or first_lower in ALPHA3_US_CA_TOKENS
            or first_upper in ALPHA3_TO_ALPHA2
            or first_lower in NON_CITY_PHRASES
        )
        # A handful of real city names are also full US-state/CA-province
        # names ("New York", "Washington") — the checks above alone would
        # always read these as "not a city." When a *different* token
        # elsewhere in the string is itself a distinct, valid state/province
        # token, that's independent confirmation the first token is being
        # used as a place name rather than as the jurisdiction itself (a
        # region can't sensibly equal itself twice in one location string),
        # so the first-token-as-city reading wins instead. This only fires
        # for the specific name-collision case — it does not affect any
        # other US_STATE_TOKENS/CA_PROVINCE_TOKENS first-token match, e.g.
        # "California, USA" still correctly yields city=None.
        if is_recognized_non_city and (
            first_lower in US_STATE_TOKENS or first_lower in CA_PROVINCE_TOKENS
        ):
            other_tokens_lower = {t.strip().lower() for t in tokens[1:]}
            has_distinct_state_or_province_token = any(
                (t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS) and t != first_lower
                for t in other_tokens_lower
            )
            if has_distinct_state_or_province_token or (
                first_lower == "new york"
                and len(tokens) >= 3
                and ("new york" in other_tokens_lower or "ny" in other_tokens_lower)
            ):
                is_recognized_non_city = False
        # Same collision, different table: a handful of real US city names
        # are also full country names ("Lebanon, TN", "Jordan, MN",
        # "Mexico, ME", "Chile, WI", "Panama, NY" — resolve_country_from_
        # location prioritizes the state/province reading for these, same
        # pre-existing trade-off noted below for the US/CA 2-letter-code
        # collisions). A trailing US-state/CA-province token elsewhere in
        # the string is the same independent confirmation as the guard
        # above — a country can't sensibly be its own trailing
        # jurisdiction — so it wins here too, just against
        # ISO_NAME_TO_CODE/LOCATION_ALIASES instead of US_STATE_TOKENS/
        # CA_PROVINCE_TOKENS. Deliberately not merged into the guard above:
        # keeping the trigger conditions (which table first_lower hit)
        # separate keeps each easy to reason about on its own.
        #
        # Gated to LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY, NOT the
        # full LOCATION_ALIASES table — confirmed live: "USA, VA, McLean"
        # was misfiring this guard (reading "USA" as a possible city
        # just because "VA" followed it), since "usa"/"us"/"uk"/"korea"/
        # etc. are never real place names anywhere, only "England"/
        # "Scotland"/"Wales"/"Holland"/"New York City" among
        # LOCATION_ALIASES' keys are genuinely also real US/CA town
        # names (verified against the gazetteer — see that set's own
        # comment).
        if is_recognized_non_city and (
            first_lower in ISO_NAME_TO_CODE
            or first_lower in LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY
        ):
            other_tokens_lower = {t.strip().lower() for t in tokens[1:]}
            has_state_or_province_token = any(
                t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS for t in other_tokens_lower
            )
            if has_state_or_province_token:
                is_recognized_non_city = False
        # "<ST>, <City>, ..." — the reverse of the far more common "<City>,
        # <ST>" order ("TX, Austin, 11501 Alterra Pkwy STE 500", "NC,
        # Raleigh, 701 Corporate Center Dr STE 200", "NJ, Morris Plains,
        # 115 Tabor Rd"). is_recognized_non_city already correctly leaves
        # city=None here (tokens[0] is a real state token), but nothing
        # upstream ever looks at tokens[1] as the city this shape actually
        # has. Scoped narrowly to tokens[0] being a genuine, uncollided
        # US-state/CA-province token (is_recognized_non_city still True
        # after both collision guards above — a collided token means
        # tokens[0] IS the city, handled by the unconditional "if not
        # is_recognized_non_city" below, not this branch), and only when
        # tokens[1] itself isn't ALSO a recognized non-city token (a real
        # "<ST>, <ST2>, ..." or "<ST>, <Country>, ..." string has no city
        # here to extract, and must not have one guessed).
        if (
            is_recognized_non_city
            and (first_lower in US_STATE_TOKENS or first_lower in CA_PROVINCE_TOKENS)
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in ISO_NAME_TO_CODE
                or second_lower in NON_CITY_PHRASES
                or second_lower == "remote"
                or second_lower == "united states"
            )
            # region is set regardless of whether tokens[1] turns out to
            # be a real city or a known non-city phrase ("Utah, Work at
            # Home" still means Utah even though "Work at Home" isn't a
            # city) — confirmed live: this used to be bundled into the
            # same `if not second_is_non_city` guard as `city`, so a
            # string like "Utah Work at Home" (after
            # LEADING_WORD_REMOTE_SUFFIX_RE's comma insertion) correctly
            # left city=None but ALSO wrongly left region=None, even
            # though tokens[0]="utah" is an unambiguous, confirmed state
            # token independent of what tokens[1] contains.
            region = first
            if not second_is_non_city:
                city = second

        # Same reversed shape, bare-alpha2-country-code-first instead of
        # state/province-first ("GB,Manchester", "AM,Yerevan",
        # "CN,Shenzhen") or alpha-3 code first ("IND, Gurgaon"). No region assignment here — unlike the
        # state/province case above, tokens[0] is a whole country, not a
        # sub-national region, so `region` (which elsewhere in this
        # function only ever holds a state/province) stays unset;
        # country_code already carries this signal separately.
        if (
            city is None
            and is_recognized_non_city
            and (first_lower in BARE_ALPHA2_CODE_TO_COUNTRY or first_upper in ALPHA3_TO_ALPHA2)
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_upper = second.upper()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in ISO_NAME_TO_CODE
                or second_lower in BARE_ALPHA2_CODE_TO_COUNTRY
                or second_upper in ALPHA3_TO_ALPHA2
                or second_lower in NON_CITY_PHRASES
                or second_lower == "remote"
            )
            if not second_is_non_city:
                city = second

        # Same reversed shape again, full country NAME first instead of a
        # bare alpha-2 code ("Ireland, Limerick", "India, Bangalore",
        # "Philippines, Manila", "Netherlands, Amsterdam", "China,
        # Shanghai", "Canada, Vancouver", "Italy, Milan") — 284 rows
        # sampled from live pool data where country_code already resolved
        # correctly (via ISO_NAME_TO_CODE) but city stayed None, since
        # nothing extracted tokens[1] as the city this shape actually has.
        # No region assignment, same reasoning as the bare-alpha2 branch
        # Same reversed shape again, full country NAME or non-ambiguous country
        # ALIAS first ("UK, Bristol", "UAE, Dubai", "USA, Atlanta") instead of
        # a bare alpha-2 code.
        if (
            city is None
            and is_recognized_non_city
            and (
                first_lower in ISO_NAME_TO_CODE
                or (
                    first_lower in LOCATION_ALIASES
                    and first_lower not in LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY
                )
            )
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in ISO_NAME_TO_CODE
                or second_lower in BARE_ALPHA2_CODE_TO_COUNTRY
                or second_lower in NON_CITY_PHRASES
                or second_lower == "remote"
            )
            if not second_is_non_city:
                city = second

        # City-states / country-capitals sharing the country's name ("Singapore, Singapore",
        # "Monaco, Monaco", "Luxembourg, Luxembourg", "Djibouti, Djibouti", "San Marino, San Marino",
        # "Kuwait, Kuwait", "Panama, Panama", "Guatemala, Guatemala").
        if (
            city is None
            and is_recognized_non_city
            and len(tokens) >= 2
            and first_lower == tokens[1].strip().lower()
            and (first_lower in ISO_NAME_TO_CODE or first_lower in LOCATION_ALIASES)
        ):
            city = first
            country_code = ISO_NAME_TO_CODE.get(first_lower) or LOCATION_ALIASES.get(first_lower)

        # "<CountryAlias>, <ST>, <City>" — 3-token, country-alias-first
        # instead of state/province-first ("USA, VA, McLean", "US, CO,
        # Longmont", "CAN, ON, London", "US, New Mexico, Albuquerque").
        # tokens[0] resolving via LOCATION_ALIASES/ALPHA3_US_CA_TOKENS to
        # US/CA (not a bare state/province token, which the branch above
        # already covers, and not a bare ISO2 code, which the branch
        # above THAT covers) means tokens[1] is the real region and
        # tokens[2] the real city — currently nothing extracts either, so
        # city fell back to the opaque "USA"/"US"/"CAN" alias token
        # itself once city ends up staying None through every branch
        # above. Scoped to exactly 3 tokens: a 2-token "USA, VA" has no
        # city to extract (handled correctly by the unconditional "if
        # not is_recognized_non_city" fallback leaving city=None), and
        # >3 tokens risk the 3rd token being an address fragment rather
        # than the city — safer to decline than guess there.
        first_maps_to_us_or_ca = LOCATION_ALIASES.get(first_lower) in (
            "US",
            "CA",
        ) or ALPHA3_US_CA_TOKENS.get(first_lower) in ("US", "CA")
        if city is None and is_recognized_non_city and first_maps_to_us_or_ca and len(tokens) == 3:
            second = tokens[1].strip()
            second_lower = second.lower()
            third = tokens[2].strip()
            third_lower = third.lower()
            if (second_lower in US_STATE_TOKENS or second_lower in CA_PROVINCE_TOKENS) and (
                third_lower not in NON_CITY_PHRASES
                and third_lower not in US_STATE_TOKENS
                and third_lower not in CA_PROVINCE_TOKENS
                and third_lower not in LOCATION_ALIASES
                and third_lower not in ISO_NAME_TO_CODE
            ):
                city = third
                region = second

        # Non-city phrase first ("Remote, Los Angeles", "Virtual, Seattle").
        # When tokens[0] is in NON_CITY_PHRASES and tokens[1] is not a non-city phrase,
        # extract tokens[1] as the city (or region if it is a state/province).
        if (
            city is None
            and is_recognized_non_city
            and first_lower in NON_CITY_PHRASES
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_upper = second.upper()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in ISO_NAME_TO_CODE
                or second_lower in BARE_ALPHA2_CODE_TO_COUNTRY
                or second_upper in ALPHA3_TO_ALPHA2
                or second_lower in NON_CITY_PHRASES
            )
            if not second_is_non_city:
                city = second
            elif second_lower in US_STATE_TOKENS or second_lower in CA_PROVINCE_TOKENS:
                region = second

        if not is_recognized_non_city and city is None:
            city = first

    # Many US-state/CA-province 2-letter tokens are themselves valid ISO
    # country codes for a different country ("DE" Delaware/Germany, "IN"
    # Indiana/India, "CA" California/Canada — 26 US + 5 CA collisions in
    # total). resolve_country_from_location() already has to make a call on
    # this ambiguity (it prioritizes the state/province reading over the ISO
    # country reading — a deliberate, pre-existing trade-off, not something
    # this function should relitigate). Gating region extraction on
    # country_code actually having resolved to US/CA keeps region
    # consistent with whatever call country resolution already made: a
    # token this function would extract as `region` is never one that
    # country resolution itself treated as signaling a non-US/CA country.
    # It does NOT independently correct a case where country_code itself is
    # wrong (e.g. "Berlin, DE" still resolves country_code to "US", so
    # region="DE" is still set) — that's resolve_country_from_location's
    # trade-off to own, not a new problem region extraction introduces on
    # top of it. What this guard does prevent: region_country_matches being
    # False (country_code resolved to neither "US" nor "CA" — e.g. a fuller
    # signal elsewhere in the string won a higher-priority match) never gets
    # silently overridden by a lower-confidence trailing 2-letter token.
    region_country_matches = country_code in ("US", "CA")
    if region_country_matches:
        if len(tokens) == 1:
            first_lower = tokens[0].lower()
            if first_lower in US_STATE_TOKENS or first_lower in CA_PROVINCE_TOKENS:
                region = tokens[0]
        elif len(tokens) == 2:
            # A bare "City, ST" shape ("Washington, DC", "Toronto, ON") —
            # the region is the trailing token itself, tokens[-1]. The >= 3
            # branch below instead looks at tokens[-2] for a "City, Region,
            # Country" shape, and reusing that same index here would
            # silently read the *city* token back as its own region for any
            # 2-token string (since tokens[-2] == tokens[0] when there are
            # only two elements) — this is exactly the shape that most needs
            # region populated, since it's often the only disambiguating
            # signal available for an otherwise ambiguous city name (e.g.
            # three US towns are named "Washington"; without "DC" from this
            # branch, town_resolver.py can't tell them apart and must
            # refuse to guess).
            last = tokens[-1].strip()
            last_lower = last.lower()
            if last_lower in US_STATE_TOKENS or last_lower in CA_PROVINCE_TOKENS:
                region = last
        elif len(tokens) >= 3:
            second_to_last = tokens[-2].strip()
            second_to_last_lower = second_to_last.lower()
            if (
                second_to_last_lower in US_STATE_TOKENS
                or second_to_last_lower in CA_PROVINCE_TOKENS
            ):
                region = second_to_last
            else:
                last = tokens[-1].strip()
                last_lower = last.lower()
                if (
                    last_lower in US_STATE_TOKENS
                    or last_lower in CA_PROVINCE_TOKENS
                ) and VENUE_PREFIX_RE.search(tokens[0]):
                    region = last
                    city = second_to_last

    # Correct the specific collision CITY_REGION_COLLISION_TO_COUNTRY was
    # derived for: city/region resolved to a real-looking US-state/CA-
    # province pair ("Bangalore, IN"), but that region code is ALSO a
    # different country's ISO code, and this exact (city, code) pair has
    # no matching US/CA town while having exactly one match in the
    # collided-with country (see that table's own comment for the full
    # derivation method). Only ever narrows a US/CA reading to a more
    # specific real country — never touches country_code when it already
    # resolved to anything else, and never invents a city/region that
    # wasn't already there. region is cleared (not left as the stale
    # "IN") since region elsewhere in this file only ever means a real
    # US-state/CA-province code, and "IN" no longer means that once
    # country_code becomes India.
    if country_code in ("US", "CA") and city is not None:
        # NFD-fold accents before the lookup ("münchen" -> "munchen") —
        # the table's keys are derived from GeoNames' ascii_name, which
        # is already unaccented, so an accented city string would
        # otherwise silently miss a real entry (confirmed live:
        # "München, DE" stayed unmatched even though "munich"/"muenchen"
        # both resolve correctly). Same fold_accents approach as
        # resolve_country_from_location's own NFD pass above and
        # town_resolver.py's _fold_accents — safe here for the same
        # reason noted there: this only extracts a lookup key, it can
        # never merge two genuinely different places.
        city_folded = "".join(
            ch
            for ch in unicodedata.normalize("NFD", city)
            if unicodedata.category(ch) != "Mn"
        )
        city_keys = (city_folded.casefold(), city.casefold())
        # Try `region` first when it was extracted (the common case), but
        # also scan every raw token — confirmed live: "Lima, LIM, PE,
        # 15008" never populated `region` at all (tokens[-2]="LIM" isn't
        # a recognized state/province token, so the region-extraction
        # tiers above legitimately left it None), yet "pe" is still
        # sitting right there in tokens as the real collision code this
        # table exists to catch. Scanning tokens directly is strictly a
        # superset of the region-only check, so this replaces rather than
        # supplements it.
        candidate_codes = ([region.casefold()] if region else []) + [
            t.lower() for t in tokens if t.lower() != city.lower()
        ]
        corrected_country = None
        matched_code = None
        for code in candidate_codes:
            for city_key in city_keys:
                corrected_country = CITY_REGION_COLLISION_TO_COUNTRY.get((city_key, code))
                if corrected_country is not None:
                    matched_code = code
                    break
            if corrected_country is not None:
                break
        if corrected_country is not None:
            country_code = corrected_country
            if region and region.lower() == matched_code:
                region = None

    return ParsedLocation(
        raw=raw,
        normalized_key=normalized_key,
        city=city,
        region=region,
        country_code=country_code,
        is_remote=is_remote,
    )
