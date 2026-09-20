"""Location-string cleanup helpers, run before parse_location's tokenizer
sees the string — strip noise tokens (street addresses, store/facility
IDs, ZIPs) and restore missing city/state commas so the conservative
matching tiers in resolve.py / parse.py get a cleaner input than they
were designed to see through.
"""

from __future__ import annotations

import re

from scraper.location.data import (
    ALPHA3_TO_ALPHA2,
    CA_PROVINCE_TOKENS,
    COUNTRY_NAMES,
    ISO_NAME_TO_CODE,
    LOCATION_ALIASES,
    NON_CITY_PHRASES,
    US_CA_COUNTRY_COLLISION_CODES,
    US_STATE_TOKENS,
)
from scraper.location.regexes import (
    CAN_SPACE_PROV_CITY_RE,
    CITY_DASH_COUNTRY_CODE_RE,
    CITY_DASH_STATE_RE,
    CITY_ST_FACILITY_RE,
    COLON_STREET_CITY_RE,
    COUNTRY_DASH_3PART_RE,
    COUNTRY_ST_DASH_RE,
    COUNTRY_STATE_WORD_DASH_RE,
    FOUR_SEASONS_PREFIX_RE,
    FRENCH_STREET_ADDRESS_PREFIX_RE,
    HOME_OFFICE_STORE_RE,
    HUB_SUFFIX_RE,
    ISO3_DASH_CITY_RE,
    ISO3_REGION_CITY_RE,
    LEADING_FACILITY_ID_DASH_RE,
    LEADING_ISO2_REGION_DASH_RE,
    LEADING_ORG_REGION_PREFIX_RE,
    LEADING_REMOTE_DASH_RE,
    LEADING_SPACE_STATE_DASH_RE,
    LEADING_WORD_DASH_RE,
    LEADING_WORD_REMOTE_SUFFIX_RE,
    LOWES_PREFIX_RE,
    METRO_AREA_RE,
    NGR_STORE_RE,
    OFFICE_SUFFIX_RE,
    REMOTE_KEYWORD_RE,
    SERVICES_OFFICE_PREFIX_RE,
    STORE_ID_PREFIX_RE,
    STREET_ADDRESS_PREFIX_RE,
    SYSCO_PREFIX_RE,
    TRAILING_ADDRESS_RE,
    TRAILING_ATTENDANCE_POLICY_RE,
    TRAILING_CA_POSTAL_CODE_RE,
    TRAILING_DASH_STATE_PAREN_ZIP_RE,
    TRAILING_FACILITY_NO_DASH_RE,
    TRAILING_MORE_RE,
    TRAILING_PAREN_CITY_REGION_RE,
    TRAILING_PAREN_CODE_RE,
    TRAILING_SHORT_CODE_RE,
    TRAILING_SPACE_STATE_RE,
    TRAILING_STATE_DASH_SUFFIX_RE,
    TRAILING_STORE_SUFFIX_RE,
    TRAILING_UK_POSTAL_CODE_RE,
    TRAILING_ZIP_RE,
    UNIQLO_PREFIX_RE,
)


def matches_word(normalized: str, phrase: str) -> bool:
    escaped = re.escape(phrase)
    return re.search(rf"(?:^|[^a-z]){escaped}(?:[^a-z]|$)", normalized) is not None


_STREET_ADDRESS_SEGMENT_RE = re.compile(
    r"^\d|\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|"
    r"parkway|pkwy|highway|hwy|circle|cir|court|ct|place|pl|square|sq)\b\.?"
    r"(?:\s+(?:north|south|east|west|n|s|e|w|ne|nw|se|sw)\b\.?)?\s*$",
    re.IGNORECASE,
)


def _looks_like_street_address(segment: str) -> bool:
    """True for a dash-separated segment that's a street address rather
    than a place name — used by clean_location_for_parsing's org-region-
    prefix reorder to drop a trailing address segment ("8th Street NE",
    "1 Denison") so the real city (the segment before it) is what gets
    extracted, not the address itself."""
    return _STREET_ADDRESS_SEGMENT_RE.search(segment) is not None


def _leading_collision_code_has_explicit_country_elsewhere(
    leading_code: str, rest_of_string: str
) -> bool:
    """True when leading_code is a US-state/CA-province collision code
    ("de", "in", "ca", ...) AND rest_of_string already spells out a real
    country name as its own comma-separated token ("Germany" after "DE").

    Used by both leading-dash branches in clean_location_for_parsing to
    detect exactly this ambiguous case ("DE - Berlin, Germany") and strip
    the leading code WITHOUT reordering it into its own comma-separated
    token, leaving "Berlin, Germany" instead of "Berlin, DE, Germany".

    NOTE: resolve_country_from_location's own US/CA collision tier was
    later taught to check for an explicit country-name token itself (see
    the "winning_token"/explicit_country check there), which makes this
    function's country-correctness purpose redundant now — "Berlin, DE,
    Germany" resolves to "DE" correctly either way. This function is kept
    because it still improves `city` quality beyond what that later fix
    covers alone: stripping here lets city extraction see "Berlin" as a
    clean tokens[0], instead of the opaque "DE - Berlin" a bare reorder
    (or withholding the whole transform) would otherwise leave behind.
    """
    if leading_code.lower() not in US_CA_COUNTRY_COLLISION_CODES:
        return False
    return any(
        t.strip().lower() in ISO_NAME_TO_CODE for t in rest_of_string.split(",") if t.strip()
    )


def clean_location_for_parsing(raw: str) -> str:
    """Strip noise tokens (street address, store/facility ID, trailing ZIP)
    and insert a missing city/state comma, all so the existing conservative
    tiers in resolve_country_from_location and parse_location's own
    tokens[0]-as-city rule get a cleaner input than they were designed to
    see through. Pattern-based only — never guesses a city/country, just
    removes junk or restores an obviously-missing delimiter. Returns raw
    unchanged if nothing matches, so a string with none of these patterns
    parses exactly as before this function existed.
    """
    cleaned = raw
    org_region_match = LEADING_ORG_REGION_PREFIX_RE.match(cleaned)
    if org_region_match:
        # "AMER - Canada - Alberta - Calgary - 8th Street NE" / "AMER -
        # United States - Georgia - Offsite/Home" / "EMEA - Germany -
        # Munich - Balanstrasse" / "APAC - India - New Delhi" — a sales-
        # region-grouping ATS convention with no comma anywhere in the
        # string, so the tokenizer everywhere else in this file never
        # separates it at all. Reorders the dash-separated segments after
        # the org-region prefix into the comma-separated shape every
        # downstream tier already understands: drops a trailing segment
        # that's pure noise (NON_CITY_PHRASES, e.g. "Offsite/Home") or
        # that looks like a street address (leading digit, or ending in a
        # common street-suffix word — "8th Street NE", "1 Denison"), then
        # emits "<last real segment>, <country>" — deliberately NOT trying
        # to also recover a US/CA state or a non-US/CA sub-national region
        # from a middle segment, since a segment here can be a full state
        # name, a 2-letter code, or a country-specific region name/number
        # ("SanJose", numeric codes) with no reliable way to tell which
        # from shape alone; the trailing segment (the real city, when
        # present) is the one signal safe to extract unambiguously.
        rest = cleaned[org_region_match.end() :]
        segments = [s.strip() for s in re.split(r"\s*-\s*", rest) if s.strip()]
        if len(segments) >= 2:
            country_segment = segments[0]
            trailing_segments = segments[1:]
            while trailing_segments and (
                trailing_segments[-1].lower() in NON_CITY_PHRASES
                or _looks_like_street_address(trailing_segments[-1])
            ):
                trailing_segments.pop()
            if trailing_segments:
                cleaned = f"{trailing_segments[-1]}, {country_segment}"
            else:
                cleaned = country_segment

    paren_city_region = TRAILING_PAREN_CITY_REGION_RE.match(cleaned)
    if paren_city_region:
        second_token = paren_city_region.group(3).strip().lower()
        if (
            second_token in US_STATE_TOKENS
            or second_token in CA_PROVINCE_TOKENS
            or second_token in LOCATION_ALIASES
            or second_token.upper() in COUNTRY_NAMES
        ):
            cleaned = f"{paren_city_region.group(2).strip()}, {paren_city_region.group(3).strip()}"

    dash_state_paren_zip = TRAILING_DASH_STATE_PAREN_ZIP_RE.match(cleaned)
    if dash_state_paren_zip and dash_state_paren_zip.group(2).strip().lower() in (
        US_STATE_TOKENS | CA_PROVINCE_TOKENS
    ):
        city_segment = dash_state_paren_zip.group(1).strip()
        state_segment = dash_state_paren_zip.group(2).strip()
        cleaned = f"{city_segment}, {state_segment}"

    cleaned = TRAILING_PAREN_CODE_RE.sub(")", cleaned)
    cleaned = TRAILING_ZIP_RE.sub("", cleaned)
    cleaned = TRAILING_CA_POSTAL_CODE_RE.sub("", cleaned)
    cleaned = TRAILING_UK_POSTAL_CODE_RE.sub(r", GB", cleaned)
    cleaned = TRAILING_SHORT_CODE_RE.sub("", cleaned)
    cleaned = TRAILING_ATTENDANCE_POLICY_RE.sub("", cleaned)
    cleaned = TRAILING_MORE_RE.sub("", cleaned)
    cleaned = HUB_SUFFIX_RE.sub(r", \1", cleaned)
    cleaned = METRO_AREA_RE.sub("", cleaned)
    cleaned = FOUR_SEASONS_PREFIX_RE.sub("", cleaned)
    cleaned = NGR_STORE_RE.sub("", cleaned)

    m_ho = HOME_OFFICE_STORE_RE.match(cleaned)
    if m_ho:
        cleaned = f"{m_ho.group(1)}, {m_ho.group(2)}, US"

    cleaned = OFFICE_SUFFIX_RE.sub(r", \1", cleaned)

    m_rem = LEADING_REMOTE_DASH_RE.match(cleaned)
    if m_rem:
        cleaned = m_rem.group(1).strip()

    state_dash_suffix = TRAILING_STATE_DASH_SUFFIX_RE.search(cleaned)
    if state_dash_suffix and state_dash_suffix.group(1).lower() in (
        US_STATE_TOKENS | CA_PROVINCE_TOKENS
    ):
        # Discards the suffix (e.g. "Remote" in "Atlanta, GA - Remote"),
        # which would silently lose is_remote if that were still computed
        # from this cleaned string — it isn't: parse_location computes
        # is_remote from the untouched raw string instead, specifically
        # so cleanup steps like this one can never suppress that signal.
        cleaned = cleaned[: state_dash_suffix.start()] + f", {state_dash_suffix.group(1)}"

    colon_match = COLON_STREET_CITY_RE.match(cleaned)
    if colon_match:
        cleaned = colon_match.group(1).strip()

    m_uniqlo = UNIQLO_PREFIX_RE.match(cleaned)
    if m_uniqlo:
        cleaned = f"{m_uniqlo.group(2).strip()}, {m_uniqlo.group(1).upper()}"

    cleaned = LEADING_FACILITY_ID_DASH_RE.sub("", cleaned)
    cleaned = SYSCO_PREFIX_RE.sub("", cleaned)
    cleaned = LOWES_PREFIX_RE.sub("", cleaned)
    cleaned = SERVICES_OFFICE_PREFIX_RE.sub("", cleaned)
    cleaned = STORE_ID_PREFIX_RE.sub("", cleaned)
    cleaned = FRENCH_STREET_ADDRESS_PREFIX_RE.sub("", cleaned)
    cleaned = STREET_ADDRESS_PREFIX_RE.sub("", cleaned)
    cleaned = TRAILING_STORE_SUFFIX_RE.sub("", cleaned)
    cleaned = TRAILING_FACILITY_NO_DASH_RE.sub("", cleaned)
    cleaned = TRAILING_ADDRESS_RE.sub("", cleaned)

    m_city_st_fac = CITY_ST_FACILITY_RE.match(cleaned.strip())
    if (
        m_city_st_fac
        and m_city_st_fac.group(2).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
        and len(m_city_st_fac.group(1).strip()) >= 3
        and not REMOTE_KEYWORD_RE.search(m_city_st_fac.group(1))
        and not m_city_st_fac.group(1).strip().endswith("-")
    ):
        cleaned = f"{m_city_st_fac.group(1).strip()}, {m_city_st_fac.group(2).strip()}, {m_city_st_fac.group(3).strip()}"

    # Country-State-City / Country-ST-City cleaning
    m_c_st = None
    if not LEADING_ISO2_REGION_DASH_RE.match(cleaned):
        m_c_st = COUNTRY_ST_DASH_RE.match(cleaned.strip())
        if not m_c_st:
            m_c_st = COUNTRY_STATE_WORD_DASH_RE.match(cleaned.strip())
        if not m_c_st:
            m_c_st = COUNTRY_DASH_3PART_RE.match(cleaned.strip())

    if m_c_st:
        c_raw = m_c_st.group(1).upper()
        p1 = m_c_st.group(2).strip()
        p2 = m_c_st.group(3).strip()
        c_code = "CA" if c_raw in ("CA", "CAN") else "US"
        v1 = (
            (p1.lower() in CA_PROVINCE_TOKENS)
            if c_code == "CA"
            else (p1.lower() in US_STATE_TOKENS)
        )
        v2 = (
            (p2.lower() in CA_PROVINCE_TOKENS)
            if c_code == "CA"
            else (p2.lower() in US_STATE_TOKENS)
        )

        if v1 and not v2:
            cleaned = f"{p2}, {p1}, {c_code}"
        elif not v1 and v2:
            cleaned = f"{p1}, {p2}, {c_code}"
        elif v1 and v2:
            cleaned = f"{p2}, {p1}, {c_code}"
    else:
        m_iso3_reg = ISO3_REGION_CITY_RE.match(cleaned.strip())
        if (
            m_iso3_reg
            and m_iso3_reg.group(1) in ALPHA3_TO_ALPHA2
            and m_iso3_reg.group(1) not in ("USA", "CAN")
        ):
            c2 = ALPHA3_TO_ALPHA2[m_iso3_reg.group(1)]
            c_name = COUNTRY_NAMES.get(c2, c2)
            reg = m_iso3_reg.group(2).strip()
            city = m_iso3_reg.group(3).strip()
            if city.lower() not in NON_CITY_PHRASES:
                cleaned = f"{city}, {c_name}"
            elif reg.lower() not in NON_CITY_PHRASES:
                cleaned = f"{reg}, {c_name}"
        else:
            m_iso3_city = ISO3_DASH_CITY_RE.match(cleaned.strip())
            if (
                m_iso3_city
                and m_iso3_city.group(1) in ALPHA3_TO_ALPHA2
                and m_iso3_city.group(1) not in ("USA", "CAN")
            ):
                c2 = ALPHA3_TO_ALPHA2[m_iso3_city.group(1)]
                c_name = COUNTRY_NAMES.get(c2, c2)
                city_seg = m_iso3_city.group(2).strip()
                if city_seg.lower() not in NON_CITY_PHRASES:
                    cleaned = f"{city_seg}, {c_name}"

    # Skip when the more specific "<ISO2>-<REGION>-<City>-..." ATS vendor
    # shape (all-caps region segment, e.g. "CA-QC-LONGUEUIL-J01") already
    # matches — that's resolve_country_from_location's own, more precise
    # reading of a leading "<2 letters>-" prefix, and reordering here
    # first would garble the exact structure it depends on. Also skip via
    # _leading_collision_code_has_explicit_country_elsewhere — see that
    # helper's docstring for the "DE - Berlin, Germany" case this guards.
    leading = LEADING_SPACE_STATE_DASH_RE.match(cleaned)
    if (
        leading
        and (
            leading.group(1).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
            or leading.group(1).upper() in COUNTRY_NAMES
        )
        and not LEADING_ISO2_REGION_DASH_RE.match(cleaned)
    ):
        city_segment = leading.group(2).strip()
        rest = cleaned[leading.end() :]
        if rest.startswith("-"):
            rest = ", " + rest.lstrip("- ")
        if _leading_collision_code_has_explicit_country_elsewhere(leading.group(1), rest):
            # Strip only — do not reorder the code into its own comma
            # token. See _leading_collision_code_has_explicit_country_
            # elsewhere's docstring.
            cleaned = f"{city_segment}{rest}"
        else:
            cleaned = f"{city_segment}, {leading.group(1)}{rest}"
    else:
        # Full-name variant ("Idaho - Boise", "Kansas - Great Bend") —
        # only attempted when the 2-letter-code case above didn't already
        # fire, so the two never compete over the same leading segment.
        # The membership check against the real state/province table is
        # what excludes "Remote - Toronto"/"Work at Home - Nevada"-style
        # strings (their leading segment is "remote"/"work at home", not a
        # jurisdiction name) — this reorder is scoped to a real leading
        # state/province name only, never a generic first-word-before-dash.
        word_leading = LEADING_WORD_DASH_RE.match(cleaned)
        if (
            word_leading
            and word_leading.group(1).strip().lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
            and not LEADING_ISO2_REGION_DASH_RE.match(cleaned)
        ):
            city_segment = word_leading.group(2).strip()
            rest = cleaned[word_leading.end() :]
            word_code = word_leading.group(1).strip()
            if rest.startswith("-"):
                rest = ", " + rest.lstrip("- ")
            if _leading_collision_code_has_explicit_country_elsewhere(word_code, rest):
                cleaned = f"{city_segment}{rest}"
            else:
                cleaned = f"{city_segment}, {word_code}{rest}"

    can_space = CAN_SPACE_PROV_CITY_RE.match(cleaned)
    if can_space and can_space.group(1).lower() in CA_PROVINCE_TOKENS:
        cleaned = f"{can_space.group(2).strip()}, {can_space.group(1).strip()}, CA"

    city_country_code = CITY_DASH_COUNTRY_CODE_RE.match(cleaned)
    if city_country_code and not REMOTE_KEYWORD_RE.search(city_country_code.group(1)):
        code_raw = city_country_code.group(2).upper()
        resolved_country = (
            ALPHA3_TO_ALPHA2.get(code_raw)
            if len(code_raw) == 3
            else (code_raw if code_raw in COUNTRY_NAMES else None)
        )
        if resolved_country and resolved_country.lower() not in (
            US_STATE_TOKENS | CA_PROVINCE_TOKENS
        ):
            cleaned = f"{city_country_code.group(1).strip()}, {resolved_country}"

    city_dash_state = CITY_DASH_STATE_RE.match(cleaned)
    if (
        city_dash_state
        and city_dash_state.group(2).strip().lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
        and not REMOTE_KEYWORD_RE.search(city_dash_state.group(1))
    ):
        cleaned = f"{city_dash_state.group(1).strip()}, {city_dash_state.group(2).strip()}"

    if "," not in cleaned:
        match = TRAILING_SPACE_STATE_RE.search(cleaned)
        if match and match.group(1).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS):
            cleaned = cleaned[: match.start()] + ", " + match.group(1)
        else:
            remote_suffix = LEADING_WORD_REMOTE_SUFFIX_RE.match(cleaned)
            if remote_suffix and remote_suffix.group(1).strip().lower() in (
                US_STATE_TOKENS | CA_PROVINCE_TOKENS
            ):
                state_segment = remote_suffix.group(1).strip()
                rest = cleaned[remote_suffix.start(2) :]
                cleaned = f"{state_segment}, {rest}"
    return cleaned.strip() or raw
