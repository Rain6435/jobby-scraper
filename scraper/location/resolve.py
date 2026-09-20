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
    CA_PROVINCE_TOKENS,
    COUNTRY_NAMES,
    LOCATION_ALIASES,
    US_STATE_TOKENS,
    ALPHA3_TO_ALPHA2,
    BARE_ALPHA2_CODE_TO_COUNTRY,
    BARE_CITY_NAME_TO_COUNTRY,
    ISO_NAME_TO_CODE,
    LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY,
)
from scraper.location.regexes import (
    COUNTRY_NAMES_COMBINED_RE,
    LEADING_ISO2_DOT_RE,
    LEADING_ISO2_REGION_DASH_RE,
    LEADING_ISO3_DASH_RE,
    LOCATION_ALIASES_COMBINED_RE,
    PAREN_RE,
    TRAILING_ALPHA3_RE,
    TRAILING_STATE_RE,
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
    # all plain ASCII. Safe here specifically because this function only
    # extracts a country *signal* from the string — unlike parse_location's
    # normalized_key (identity/dedup), folding accents can never merge two
    # genuinely different places into the same resolved country by mistake,
    # it only lets an accented spelling reach a table that was already
    # reachable via its unaccented spelling.
    folded = unicodedata.normalize("NFD", location)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    normalized = folded.lower()

    leading_iso2 = LEADING_ISO2_DOT_RE.match(normalized)
    if leading_iso2 and leading_iso2.group(1).upper() in COUNTRY_NAMES:
        return leading_iso2.group(1).upper()

    leading_iso3 = LEADING_ISO3_DASH_RE.match(normalized)
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
        code = ISO_NAME_TO_CODE.get(token)
        if code:
            return code

    if LOCATION_ALIASES_COMBINED_RE.search(without_parens) is not None:
        for alias, code in LOCATION_ALIASES.items():
            if matches_word(without_parens, alias):
                return code
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

    # Lowest-priority fallback: the whole string, once stripped, is nothing
    # but a bare city name with no country/province/ISO signal at all (e.g.
    # "Montreal", "Toronto"). Whole-string match only — not a token/substring
    # scan — so this never fires on a city name embedded in a longer string
    # ("Montreal Office" stays None; "Montreal, Canada" already resolved via
    # the name-matching tier above, long before reaching here).
    bare_city_code = BARE_CITY_NAME_TO_COUNTRY.get(normalized.strip())
    if bare_city_code:
        return bare_city_code

    return None
