"""Location-string cleanup helpers, run before parse_location's tokenizer
sees the string — strip noise tokens (street addresses, store/facility
IDs, ZIPs) and restore missing city/state commas so the conservative
matching tiers in resolve.py / parse.py get a cleaner input than they
were designed to see through.
"""

from __future__ import annotations

import re

from scraper.location.data import (
    CA_PROVINCE_TOKENS,
    US_STATE_TOKENS,
    ISO_NAME_TO_CODE,
    US_CA_COUNTRY_COLLISION_CODES,
)
from scraper.location.regexes import (
    LEADING_FACILITY_ID_DASH_RE,
    LEADING_ISO2_REGION_DASH_RE,
    LEADING_SPACE_STATE_DASH_RE,
    LEADING_WORD_DASH_RE,
    LEADING_WORD_REMOTE_SUFFIX_RE,
    STORE_ID_PREFIX_RE,
    STREET_ADDRESS_PREFIX_RE,
    TRAILING_CA_POSTAL_CODE_RE,
    TRAILING_DASH_STATE_PAREN_ZIP_RE,
    TRAILING_PAREN_CODE_RE,
    TRAILING_SHORT_CODE_RE,
    TRAILING_SPACE_STATE_RE,
    TRAILING_STATE_DASH_SUFFIX_RE,
    TRAILING_STORE_SUFFIX_RE,
    TRAILING_ZIP_RE,
)


def matches_word(normalized: str, phrase: str) -> bool:
    escaped = re.escape(phrase)
    return re.search(rf"(?:^|[^a-z]){escaped}(?:[^a-z]|$)", normalized) is not None



def leading_collision_code_has_explicit_country_elsewhere(
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
    cleaned = TRAILING_SHORT_CODE_RE.sub("", cleaned)

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

    cleaned = STREET_ADDRESS_PREFIX_RE.sub("", cleaned)
    cleaned = STORE_ID_PREFIX_RE.sub("", cleaned)
    cleaned = TRAILING_STORE_SUFFIX_RE.sub("", cleaned)
    cleaned = LEADING_FACILITY_ID_DASH_RE.sub("", cleaned)

    # Skip when the more specific "<ISO2>-<REGION>-<City>-..." ATS vendor
    # shape (all-caps region segment, e.g. "CA-QC-LONGUEUIL-J01") already
    # matches — that's resolve_country_from_location's own, more precise
    # reading of a leading "<2 letters>-" prefix, and reordering here
    # first would garble the exact structure it depends on. Also skip via
    # leading_collision_code_has_explicit_country_elsewhere — see that
    # helper's docstring for the "DE - Berlin, Germany" case this guards.
    leading = LEADING_SPACE_STATE_DASH_RE.match(cleaned)
    if (
        leading
        and leading.group(1).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
        and not LEADING_ISO2_REGION_DASH_RE.match(cleaned)
    ):
        city_segment = leading.group(2).strip()
        rest = cleaned[leading.end():]
        if leading_collision_code_has_explicit_country_elsewhere(leading.group(1), rest):
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
            rest = cleaned[word_leading.end():]
            word_code = word_leading.group(1).strip()
            if leading_collision_code_has_explicit_country_elsewhere(word_code, rest):
                cleaned = f"{city_segment}{rest}"
            else:
                cleaned = f"{city_segment}, {word_code}{rest}"

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
                rest = cleaned[remote_suffix.start(2):]
                cleaned = f"{state_segment}, {rest}"
    return cleaned.strip() or raw


