"""Country resolution: resolve_country_from_location() maps a free-text
job-location string to an ISO alpha-2 country code, or None when nothing
confidently matches. Port of countryResolver.ts's resolveCountryFromLocation
— keep the matching order and alias tables identical to that file.
"""

from __future__ import annotations

import re
import unicodedata

from scraper.location.cleaning import matches_word
from scraper.location.data import (
    ALPHA3_TO_ALPHA2,
    BARE_ALPHA2_CODE_TO_COUNTRY,
    BARE_CITY_NAME_TO_COUNTRY,
    CA_PROVINCE_TOKENS,
    COUNTRY_NAMES,
    ISO_NAME_TO_CODE,
    LOCATION_ALIASES,
    LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY,
    SUB_NATIONAL_REGION_TO_COUNTRY,
    US_STATE_TOKENS,
)
from scraper.location.regexes import (
    COUNTRY_NAMES_COMBINED_RE,
    DESJARDINS_RE,
    DNU_PREFIX_RE,
    FOUR_SEASONS_PREFIX_RE,
    FRENCH_STREET_ADDRESS_PREFIX_RE,
    HOME_OFFICE_STORE_RE,
    HUB_SUFFIX_RE,
    LEADING_ISO2_DOT_RE,
    LEADING_ISO2_REGION_DASH_RE,
    LEADING_ISO3_RE,
    LEADING_REMOTE_DASH_RE,
    LEADING_WORD_REMOTE_SUFFIX_RE,
    LOCATION_ALIASES_COMBINED_RE,
    LOWES_PREFIX_RE,
    METRO_AREA_RE,
    NGR_STORE_RE,
    OFFICE_SUFFIX_RE,
    PAREN_RE,
    STORE_ID_PREFIX_RE,
    STREET_ADDRESS_PREFIX_RE,
    SYSCO_PREFIX_RE,
    TRAILING_ADDRESS_RE,
    TRAILING_ALPHA3_RE,
    TRAILING_ATTENDANCE_POLICY_RE,
    TRAILING_CA_POSTAL_CODE_RE,
    TRAILING_CITY_ADDRESS_RE,
    TRAILING_FACILITY_NO_DASH_RE,
    TRAILING_MORE_RE,
    TRAILING_SHORT_CODE_RE,
    TRAILING_STATE_RE,
    TRAILING_STORE_SUFFIX_RE,
    TRAILING_UK_POSTAL_CODE_RE,
    TRAILING_ZIP_RE,
    UNIQLO_PREFIX_RE,
)


def resolve_country_from_location(location: str | None) -> str | None:
    """Resolve a free-text job location string to an ISO alpha-2 country
    code. Returns None — never a guess — when nothing confidently matches;
    callers must treat None as "unknown," never default it to a country.

    Port of countryResolver.ts's resolveCountryFromLocation(); keep the
    matching order and alias tables identical to that file.
    """
    if not location or not location.strip():
        return None

    if DESJARDINS_RE.search(location):
        return "CA"
    m_uniqlo = UNIQLO_PREFIX_RE.match(location)
    if m_uniqlo and m_uniqlo.group(1).lower() in US_STATE_TOKENS:
        return "US"

    location = TRAILING_MORE_RE.sub("", location)
    location = HUB_SUFFIX_RE.sub(r", \1", location)
    location = METRO_AREA_RE.sub("", location)
    location = FOUR_SEASONS_PREFIX_RE.sub("", location)
    location = SYSCO_PREFIX_RE.sub("", location)
    location = STORE_ID_PREFIX_RE.sub("", location)
    m_rem = LEADING_REMOTE_DASH_RE.match(location)
    if m_rem:
        location = str(m_rem.group(1)).strip()
    m_ho = HOME_OFFICE_STORE_RE.match(location)
    if m_ho:
        location = f"{m_ho.group(1)}, {m_ho.group(2)}, US"
    location = OFFICE_SUFFIX_RE.sub(r", \1", location)
    location = LOWES_PREFIX_RE.sub("", location)
    location = TRAILING_FACILITY_NO_DASH_RE.sub("", location)
    location = NGR_STORE_RE.sub("", location)
    location = TRAILING_UK_POSTAL_CODE_RE.sub(r", GB", location)
    location = TRAILING_ZIP_RE.sub("", location)
    location = TRAILING_CA_POSTAL_CODE_RE.sub("", location)
    location = TRAILING_SHORT_CODE_RE.sub("", location)
    location = TRAILING_ATTENDANCE_POLICY_RE.sub("", location)
    location = TRAILING_ADDRESS_RE.sub("", location)
    location = TRAILING_CITY_ADDRESS_RE.sub("", location)
    location = STREET_ADDRESS_PREFIX_RE.sub("", location)
    location = FRENCH_STREET_ADDRESS_PREFIX_RE.sub("", location)
    location = DNU_PREFIX_RE.sub("", location)
    location = TRAILING_STORE_SUFFIX_RE.sub("", location)

    remote_suffix = LEADING_WORD_REMOTE_SUFFIX_RE.match(location)
    if remote_suffix and remote_suffix.group(1).strip().lower() in (
        US_STATE_TOKENS | CA_PROVINCE_TOKENS
    ):
        state_segment = str(remote_suffix.group(1)).strip()
        rest = location[remote_suffix.start(2) :]
        location = f"{state_segment}, {rest}"

    # "<ISO2>-<REGION>-<City>-..." vendor shape (e.g. "CA-QC-LONGUEUIL-J01")
    # is the one check that needs the ORIGINAL case (see
    # LEADING_ISO2_REGION_DASH_RE's comment on why all-caps is what
    # distinguishes it from a same-shaped US-domestic feed) — must run
    # before the string is lowercased below.
    leading_region = LEADING_ISO2_REGION_DASH_RE.match(location)
    if leading_region and leading_region.group(1) in COUNTRY_NAMES:
        return leading_region.group(1)

    # NFD-decompose then drop combining marks: folds "québec"/"montréal"/
    # "münchen" to their unaccented ASCII form so they match
    # CA_PROVINCE_TOKENS/ISO_NAME_TO_CODE/LOCATION_ALIASES, whose keys are
    # all plain ASCII. Recompose with NFC so non-Latin scripts (e.g. Hangul
    # syllables in "대한민국") stay intact rather than remaining decomposed Jamo.
    # Safe here specifically because this function only extracts a country *signal*
    # from the string — unlike parse_location's normalized_key (identity/dedup),
    # folding accents can never merge two genuinely different places into the same
    # resolved country by mistake, it only lets an accented spelling reach a table
    # that was already reachable via its unaccented spelling.
    folded = unicodedata.normalize("NFD", location)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    folded = unicodedata.normalize("NFC", folded)
    normalized = folded.lower()

    leading_iso2 = LEADING_ISO2_DOT_RE.match(normalized)
    if leading_iso2 and leading_iso2.group(1).upper() in COUNTRY_NAMES:
        return leading_iso2.group(1).upper()

    leading_iso3 = LEADING_ISO3_RE.match(normalized)
    if leading_iso3:
        code = ALPHA3_TO_ALPHA2.get(leading_iso3.group(1).upper())
        if code:
            return code

    paren_tokens = [m.group(1).strip() for m in PAREN_RE.finditer(normalized)]
    without_parens = PAREN_RE.sub(" ", normalized)
    tokens = [t.strip() for t in re.split(r"[,/|]", without_parens) if t.strip()]
    tokens += [t for t in paren_tokens if t]

    for token in tokens:
        # A handful of LOCATION_ALIASES keys are ALSO real US/CA town
        # names ("Holland, MI", "England, AR", "Scotland, SD", "Wales,
        # WI") — confirmed live: "Holland, MI" was resolving to "NL"
        # (Netherlands) via this tier, before the US/CA collision tier
        # further down ever got a chance to see "MI". Deferring here
        # when a real state/province token exists elsewhere in the
        # string mirrors parse_location's own city-extraction guard for
        # the identical ambiguity (_LOCATION_ALIASES_AMBIGUOUS_WITH_US_
        # CA_CITY) — every other LOCATION_ALIASES key ("usa", "uk",
        # "korea", ...) is never a real place name, so this never
        # affects those.
        if token in LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY:
            other_tokens = [t for t in tokens if t != token]
            has_state_or_province_token = any(
                t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS for t in other_tokens
            )
            if has_state_or_province_token:
                continue
        code = LOCATION_ALIASES.get(token)
        if code:
            return code

    # "<City>, <CA province>, CA, <postal code>" (e.g. "London, ON, CA,
    # N6E 1V4", "Montreal, QC, CA, H3B4G7") — a trailing bare "ca" token
    # is ambiguous between California (US_STATE_TOKENS) and Canada's ISO
    # code, and the collision-resolution tier below would wrongly read it
    # as California here: since "ca" itself is also in US_STATE_TOKENS,
    # last_us_index always lands on this same trailing token, and a
    # trailing token beats an earlier one by that tier's own "prefer the
    # trailing hit" rule regardless of what the earlier CA-province token
    # was. This is a narrower, higher-confidence signal than that general
    # tier: California is never itself followed by a *different*,
    # genuine CA-province token immediately before it (California has no
    # "province" of its own to place there), so "<distinct CA province>,
    # ca" as the final two tokens unambiguously means Canada. Checked only
    # for this exact last-two-tokens shape — does not touch any other
    # "ca" occurrence, so every ordinary "<City>, CA" California case
    # (the overwhelmingly common one) is untouched.
    if len(tokens) >= 2 and tokens[-1] == "ca":
        second_to_last = tokens[-2]
        if second_to_last in CA_PROVINCE_TOKENS and second_to_last != "ca":
            return "CA"

    # A handful of CA province names / US state names are also real city
    # names in the *other* country ("Ontario, California", "Yukon,
    # Oklahoma") — scanning left-to-right and returning on the first hit
    # would read the city-name token as the jurisdiction and misclassify
    # the whole location. Collect every US/CA hit first; when tokens from
    # only one side matched, behave exactly as before (the overwhelming
    # common case — no ambiguity to resolve). When both sides matched,
    # that's the collision case: the true region token is the trailing one
    # (the "City, Region" / "City, Region, Country" convention this same
    # function already trusts elsewhere, e.g. TRAILING_STATE_RE and
    # parse_location's tokens[-2] region extraction below), so prefer
    # whichever hit appears last in the string. Mirrors the equivalent
    # first-token-vs-distinct-token collision guard parse_location already
    # applies to city extraction, just applied here to country resolution.
    last_us_index = last_ca_index = -1
    for index, token in enumerate(tokens):
        if token in US_STATE_TOKENS:
            last_us_index = index
        if token in CA_PROVINCE_TOKENS:
            last_ca_index = index
    if last_us_index != -1 or last_ca_index != -1:
        winning_index = last_us_index if last_us_index > last_ca_index else last_ca_index
        # An explicit, full country name spelled out as its own token
        # elsewhere in the string ("China" in "Shanghai, SD, China",
        # "Netherlands" in "Amsterdam, NH, Netherlands") is a stronger
        # signal than this tier's own US/CA state/province-token guess —
        # confirmed live: both of those silently misresolved to US/CA
        # (via "SD"/"NH" respectively) even with the real country spelled
        # out right there, since this tier always returned before
        # anything downstream got a chance to see it. Safe to check
        # unconditionally (not just when the winning token happens to be
        # a US-state/CA-province/country-code collision): when the
        # explicit name and this tier's own answer agree — the
        # overwhelmingly common case, e.g. "Toronto, ON, Canada" — this
        # changes nothing, since ISO_NAME_TO_CODE["canada"] is "CA",
        # the same answer the tier below already gives.
        for other_index, other_token in enumerate(tokens):
            if other_index == winning_index:
                continue
            # "Jamaica" is excluded from this explicit-country override for
            # the same reason it's excluded from the bare-token tier below
            # — confirmed live: "JAMAICA NY STORE" hit this exact path,
            # with "ny" as the winning US token and "jamaica" as the
            # "explicit country" override, misresolving to "JM" even
            # though "ny" is real, unambiguous confirmation this is
            # Jamaica, Queens, not the country.
            if other_token == "jamaica":
                continue
            explicit_country = ISO_NAME_TO_CODE.get(other_token)
            if explicit_country:
                return explicit_country
        return "US" if last_us_index > last_ca_index else "CA"

    # Bare, non-colliding ISO alpha-2 code as its own token ("GB",
    # "GB,Manchester", "AM,Yerevan") — checked after the US/CA collision
    # tier above so a colliding code (already excluded from this table
    # anyway) can never reach here ahead of that more careful logic.
    for token in tokens:
        code = BARE_ALPHA2_CODE_TO_COUNTRY.get(token)
        if code:
            return code

    for token in tokens:
        # "Jamaica" (the country) is also a real, well-known NYC town —
        # "Jamaica, NY" (Queens) — confirmed via the gazetteer (a single
        # match, US/NY). Same collision shape LOCATION_ALIASES_AMBIGUOUS_
        # WITH_US_CA_CITY already guards for LOCATION_ALIASES keys
        # ("Holland, MI", "England, AR"), just for a full COUNTRY_NAMES
        # value instead — confirmed live: "JAMAICA NY STORE" misresolved
        # to "JM" even with "NY" sitting right there disambiguating it.
        if token == "jamaica":
            other_tokens = [t for t in tokens if t != token]
            has_state_or_province_token = any(
                t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS for t in other_tokens
            )
            if has_state_or_province_token:
                continue
        code = ISO_NAME_TO_CODE.get(token)
        if code:
            return code

    # Sub-national region token for countries outside US/CA (e.g. Jalisco -> MX,
    # Zhejiang -> CN, Bavaria -> DE, Buckinghamshire -> GB, VIC -> AU, São Paulo -> BR).
    for token in tokens:
        code = SUB_NATIONAL_REGION_TO_COUNTRY.get(token)
        if code:
            return code

    if LOCATION_ALIASES_COMBINED_RE.search(without_parens) is not None:
        for alias, code in LOCATION_ALIASES.items():
            if matches_word(without_parens, alias):
                return code
    # Word-boundary substring match against the de-parenthesized string —
    # catches phrasing like "Remote (US)", "Berlin, Germany, Hybrid",
    # "Mexico City", "Krakow, Poland Office", "Shanghai, Mainland China"
    # where the country name is a real word within a token but not the
    # WHOLE token by itself. An earlier attempt to tighten this to an
    # exact-token match (2026-09-20, to fix "Dialysis Center Of Middle
    # Georgia-Warner Robins" misresolving to Georgia the country) was
    # reverted after replaying the full live pool: it broke 67 confirmed-
    # correct resolutions of exactly this "<City>, <Country> <suffix
    # word>" / "<Country> <City>" shape (verified via
    # town_resolver.resolve_town on both versions) for every one it fixed.
    # No token-shape rule distinguishes the false positives from the
    # legitimate cases — "Dialysis Center Of Middle Georgia-Warner Robins"
    # and "Mexico City" are structurally identical (one un-comma-delimited
    # token containing a country name plus other words) — so the broader,
    # historically-tested substring match was kept. COUNTRY_NAMES_COMBINED_RE
    # gates the loop so this only runs the full COUNTRY_NAMES scan when a
    # match is structurally possible.
    if COUNTRY_NAMES_COMBINED_RE.search(without_parens) is not None:
        for code, name in COUNTRY_NAMES.items():
            if matches_word(without_parens, name.lower()):
                return code

    trailing = TRAILING_STATE_RE.search(without_parens.strip())
    if trailing:
        candidate = trailing.group(1)
        if candidate in US_STATE_TOKENS:
            return "US"
        if candidate in CA_PROVINCE_TOKENS:
            return "CA"

    # Trailing "<City>, <ISO3>" shape ("Bengaluru, IND", "Tokyo, JPN") — the
    # comma-tokenizer above only checks tokens against alias/name tables, so
    # a bare 3-letter code never matched anything until now.
    trailing_alpha3 = TRAILING_ALPHA3_RE.search(without_parens.strip())
    if trailing_alpha3:
        code = ALPHA3_TO_ALPHA2.get(trailing_alpha3.group(1).upper())
        if code:
            return code

    bare_alpha3 = ALPHA3_TO_ALPHA2.get(normalized.strip().upper())
    if bare_alpha3:
        return bare_alpha3

    # Lowest-priority fallback: the whole string, once stripped, is nothing
    # but a bare city name with no country/province/ISO signal at all (e.g.
    # "Montreal", "Toronto"). Whole-string match only — not a token/substring
    # scan — so this never fires on a city name embedded in a longer string
    # ("Montreal Office" stays None; "Montreal, Canada" already resolved via
    # the name-matching tier above, long before reaching here).
    bare_city_code = BARE_CITY_NAME_TO_COUNTRY.get(normalized.strip())
    if bare_city_code:
        return bare_city_code

    # Multi-token strings where the TRAILING token is an unambiguous bare
    # city name (e.g. "Pudong, Shanghai", "Lancaster Luminaire Building,
    # Hanoi", "City Hall, 15670 NE 85th St, Redmond"). Safe only because
    # the bare-city table itself has already guaranteed single-country
    # uniqueness for each entry — the city name is unambiguous regardless
    # of what precedes it. Also checks the trailing token with " city"
    # removed (e.g. "Quezon City" -> "quezon city" is already in the table,
    # but "davao city" -> "davao" is not, so this fallback handles it).
    if len(tokens) >= 2:
        last_token = tokens[-1]
        code = BARE_CITY_NAME_TO_COUNTRY.get(last_token)
        if not code and last_token.endswith(" city"):
            code = BARE_CITY_NAME_TO_COUNTRY.get(last_token[: -len(" city")].rstrip())
        if code:
            return code

    # Multi-token strings where the FIRST token is an unambiguous bare city
    # and the SECOND token starts with digits (a street address number),
    # indicating a "<City>, <street-number> <Street>" shape (e.g.
    # "Montréal, 2020 Robert-Bourassa", "St-Hyacinthe, 2450 Girouard GO").
    # The city is the reliable signal here; the address segment adds nothing.
    if len(tokens) >= 2 and re.match(r"^\d+\b", tokens[1]):
        code = BARE_CITY_NAME_TO_COUNTRY.get(tokens[0])
        if code:
            return code

    return None
