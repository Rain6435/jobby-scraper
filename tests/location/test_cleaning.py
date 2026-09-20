"""Tests for scraper/location/cleaning.py's clean_location_for_parsing —
noise-stripping and comma-insertion passes that run before parse_location's
tokenizer sees a raw location string.
"""

from scraper.location.cleaning import clean_location_for_parsing

# --- Preprocessing cleanup (street address / store ID / trailing ZIP / --
# --- broader remote detection), sampled from real unresolved prod rows ---


def test_clean_strips_leading_street_address_before_city():
    assert (
        clean_location_for_parsing("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
        == "Fullerton,CA"
    )
    assert (
        clean_location_for_parsing("8680 Beechmont Ave, Cincinnati,OH 45255-4710")
        == "Cincinnati,OH"
    )


def test_clean_strips_store_id_prefix():
    # Also picks up the trailing-space-state comma insertion below, since
    # both the store-ID prefix and the missing city/state comma are
    # present in these real sampled strings.
    assert clean_location_for_parsing("Store 2743142 Murrysville PA") == "Murrysville, PA"
    assert clean_location_for_parsing("Store0187 Lexington KY") == "Lexington, KY"


def test_clean_strips_trailing_zip():
    assert clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"
    assert clean_location_for_parsing("Athens, GA, US, 30606") == "Athens, GA, US"


def test_clean_is_a_noop_when_nothing_matches():
    for s in ("Toronto, ON", "Remote", "Berlin, Germany", "Mt Laurel"):
        assert clean_location_for_parsing(s) == s


def test_clean_never_returns_empty_string():
    # A pathological input that is entirely consumed by the street-address
    # pattern must fall back to the original raw string, never "" — an
    # empty city-extraction input is worse than the noisy original.
    assert clean_location_for_parsing("123 Main Street") == "123 Main Street"


# --- Trailing space-joined state/province ("Portland OR", store-ID-prefixed --
# --- "Store 2743142 Murrysville PA") — comma insertion ahead of parsing ---


def test_clean_inserts_comma_before_trailing_us_state_abbreviation():
    assert clean_location_for_parsing("Portland OR") == "Portland, OR"
    assert clean_location_for_parsing("Appleton WI") == "Appleton, WI"


def test_clean_inserts_comma_before_trailing_ca_province_abbreviation():
    assert clean_location_for_parsing("Store 6000275 Montréal QC") == "Montréal, QC"


def test_clean_trailing_space_state_requires_all_caps():
    # Lowercase/mixed-case two-letter trailing words are common English,
    # not state codes ("in", "or", "hi") — must not fire on these, or a
    # huge share of ordinary sentences would get a spurious state region.
    assert clean_location_for_parsing("Now Hiring in") == "Now Hiring in"
    assert clean_location_for_parsing("Party time hi") == "Party time hi"


def test_clean_trailing_space_state_skipped_when_string_already_has_a_comma():
    # A string that already uses commas has its own, already-correct
    # tokenization (parse_location's tokens[-1]/tokens[-2] region logic) —
    # inserting a second comma here could only ever double up or conflict
    # with that, never help it.
    assert clean_location_for_parsing("Toronto, ON") == "Toronto, ON"


# --- Canadian addresses with a trailing "CA" (ISO code) after a real CA --
# --- province token ("London, ON, CA, N6E 1V4") — previously misread as --
# --- California, since a bare "ca" token also matches US_STATE_TOKENS ---


def test_clean_strips_trailing_canadian_postal_code():
    assert clean_location_for_parsing("London, ON, CA, N6E 1V4") == "London, ON, CA"
    assert clean_location_for_parsing("Montreal, QC, CA, H3B4G7") == "Montreal, QC, CA"
    assert clean_location_for_parsing("Milton, ON, CA, L9T 0A5") == "Milton, ON, CA"


# --- Leading "<ST> - <City>" / "<ST>-<City>" ("WV - Triadelphia, 215 --
# --- Cabela Dr", "CT-WALLINGFORD, 108 LEIGUS RD") — a documented, --
# --- deliberately unhandled ambiguity in resolve_country_from_location's --
# --- own ISO2-region-dash tier (see LEADING_ISO2_REGION_DASH_RE) ---


def test_clean_reorders_leading_state_dash_to_trailing_comma_shape():
    assert (
        clean_location_for_parsing("WV - Triadelphia, 215 Cabela Dr - Retail XFR2716")
        == "Triadelphia, WV, 215 Cabela Dr - Retail XFR2716"
    )
    assert clean_location_for_parsing("WA - Fife") == "Fife, WA"
    assert (
        clean_location_for_parsing("CT-WALLINGFORD, 108 LEIGUS RD, 1ST FL")
        == "WALLINGFORD, CT, 108 LEIGUS RD, 1ST FL"
    )


def test_clean_leading_state_dash_skips_the_iso2_region_dash_ats_shape():
    # "CA-QC-LONGUEUIL-J01" / "AU-NSW-WILLIAMTOWN-001" are the OTHER
    # documented leading-dash shape (all-caps ISO2 country + region code),
    # already handled correctly and more precisely by
    # LEADING_ISO2_REGION_DASH_RE inside resolve_country_from_location —
    # must be left untouched, not reordered as if "CA"/"AU" were a US
    # state/CA province.
    assert clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"
    assert clean_location_for_parsing("AU-NSW-WILLIAMTOWN-001") == "AU-NSW-WILLIAMTOWN-001"


# --- Trailing short (1-4 digit) facility code after the state, space- --
# --- separated ("Fayetteville, NC 0388") — same failure mode as the --
# --- 5-digit ZIP case, just a shorter code ---


def test_clean_strips_trailing_short_facility_code():
    assert clean_location_for_parsing("Fayetteville, NC 0388") == "Fayetteville, NC"
    assert clean_location_for_parsing("Kahului, HI 3279") == "Kahului, HI"
    assert clean_location_for_parsing("Fremont, OH 0019") == "Fremont, OH"


def test_clean_trailing_short_code_does_not_touch_5_digit_zip():
    # 5-digit is TRAILING_ZIP_RE's job (runs first) — must not double
    # apply or disagree on the boundary.
    assert clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"


# --- Trailing digits stuck after a closing paren ("W. Jefferson, NC (W --
# --- Jefferson) 2255") — breaks the state-token match once parens strip ---


def test_clean_strips_trailing_digits_after_paren():
    assert (
        clean_location_for_parsing("W. Jefferson, NC (W Jefferson) 2255")
        == "W. Jefferson, NC (W Jefferson)"
    )
    assert (
        clean_location_for_parsing("Chandler, AZ (W Chandler) 0674")
        == "Chandler, AZ (W Chandler)"
    )


# --- Trailing "STORE - NNNN" suffix, city-first ("QUINCY STORE - 1915") --
# --- — the mirror image of the leading store-ID-prefix case ---


def test_clean_strips_trailing_store_suffix():
    assert clean_location_for_parsing("QUINCY STORE - 1915") == "QUINCY"
    assert clean_location_for_parsing("PICKERING STORE - 7238") == "PICKERING"


# --- Leading full state/province name + dash ("Idaho - Boise", "Kansas --
# --- - Great Bend") — full-name variant of the 2-letter-code case ---


def test_clean_reorders_leading_full_state_name_dash():
    assert clean_location_for_parsing("Idaho - Boise") == "Boise, Idaho"
    assert clean_location_for_parsing("Kansas - Great Bend") == "Great Bend, Kansas"


def test_clean_leading_full_state_name_dash_skips_remote_and_work_at_home():
    # "remote"/"work at home" are not state/province names — must not
    # be reordered as if they were a state preceding a dash (e.g. "Toronto, Remote").
    # Leading remote prefixes are stripped cleanly instead.
    assert clean_location_for_parsing("Remote - Toronto") == "Toronto"
    assert clean_location_for_parsing("Work at Home - Nevada") == "Nevada"


def test_clean_leading_full_state_name_dash_skips_iso2_region_dash_shape():
    # Must not compete with the 2-letter-code branch's own ISO2-region-
    # dash guard — "CA" is also a US_STATE_TOKENS member (California), so
    # without this guard the full-name branch would wrongly reorder
    # "CA-QC-LONGUEUIL-J01" too.
    assert clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"


# --- Leading zero-padded 5-digit facility ID + dash ("02319 - Grove --
# --- City Dialysis") — different vendor convention from "Store <id>" ---


def test_clean_strips_leading_5_digit_facility_id():
    assert clean_location_for_parsing("02319 - Grove City Dialysis") == "Grove City Dialysis"
    assert clean_location_for_parsing("11722 - Majestic Dialysis") == "Majestic Dialysis"


# --- Trailing "<ST> - <suffix>" after the state token ("Dallas, TX - --
# --- USA", "New Haven, CT - USA") — found while investigating why huge --
# --- cities like Dallas/Amsterdam/Shanghai weren't matching the --
# --- gazetteer: the dash-glued suffix broke tokens[-1]'s state match, --
# --- so region stayed None and town_resolver.py correctly refused to --
# --- guess among multiple same-named US towns without it ---


def test_clean_strips_trailing_state_dash_suffix():
    assert clean_location_for_parsing("Dallas, TX - USA") == "Dallas, TX"
    assert clean_location_for_parsing("Dallas, TX - Data Center") == "Dallas, TX"
    assert clean_location_for_parsing("New Haven, CT - USA") == "New Haven, CT"


def test_clean_trailing_state_dash_suffix_preserves_city_internal_dash():
    # The city itself has a dash BEFORE the comma — only the segment
    # after the LAST comma is a candidate for stripping.
    assert (
        clean_location_for_parsing("Winston- Salem, NC - USA") == "Winston- Salem, NC"
    )


# --- Trailing 6-digit international postal code (India's PIN code, --
# --- Singapore's, Vietnam's, ...) — same failure mode as the 5-digit --
# --- US ZIP case, just a different digit count, found via "Bangalore, --
# --- Karnataka, IND, 560093" staying country_code=None even though --
# --- "IND" alone (no trailing digits) resolves fine ---


def test_clean_strips_trailing_6_digit_postal_code():
    assert (
        clean_location_for_parsing("Bangalore, Karnataka, IND, 560093")
        == "Bangalore, Karnataka, IND"
    )
    assert clean_location_for_parsing("Singapore, SG, 797546") == "Singapore, SG"


def test_clean_6_digit_postal_code_does_not_touch_5_digit_us_zip():
    assert clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"
    assert clean_location_for_parsing("Athens, GA, US, 30606") == "Athens, GA, US"


# --- Trailing compass-direction suffix on a street address ("7000 --
# --- Target Pkwy N", "15800 87th St NE") — the existing street-address --
# --- prefix strip left the direction letter as an opaque tokens[0], --
# --- leaking bare "N"/"NE"/"SW"/etc. into `city` ---


def test_clean_strips_street_address_with_direction_suffix():
    assert (
        clean_location_for_parsing("15800 87th St NE, Otsego, MN 55330-6546")
        == "Otsego, MN"
    )
    assert (
        clean_location_for_parsing("356 12th St SW, Forest Lake,MN 55025-1749")
        == "Forest Lake,MN"
    )


def test_clean_street_address_direction_suffix_all_eight_directions():
    for direction in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
        cleaned = clean_location_for_parsing(f"100 Main St {direction}, Springfield, IL 62701")
        assert cleaned == "Springfield, IL", direction


def test_clean_street_address_without_direction_suffix_still_works():
    # Sanity: the original, more common shape with no direction suffix
    # at all must be completely unaffected.
    assert (
        clean_location_for_parsing("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
        == "Fullerton,CA"
    )


# --- "<FullStateName> <remote-phrase>" — space-joined, no comma or dash --
# --- at all ("Utah Work at Home", "Oregon Virtual") — distinct from the --
# --- dash-joined "<ST> - Remote" shape already handled; 60 rows sampled ---


def test_clean_inserts_comma_before_trailing_remote_phrase():
    assert clean_location_for_parsing("Utah Work at Home") == "Utah, Work at Home"
    assert clean_location_for_parsing("Oregon Virtual") == "Oregon, Virtual"
    assert (
        clean_location_for_parsing("West Virginia Work at Home")
        == "West Virginia, Work at Home"
    )


def test_clean_remote_phrase_suffix_does_not_fire_on_non_state_leading_word():
    # No real state/province name before the remote phrase — must not
    # insert a comma or claim a region.
    assert clean_location_for_parsing("Somewhere Remote") == "Somewhere Remote"


# --- "<City>-<FullStateName>(<zip>)" — no comma/space around the dash at --
# --- all, trailing zip in parens ("Laredo-Texas(78043)") — a distinct --
# --- ATS vendor shape from every other dash pattern (81 rows sampled) ---


def test_clean_reorders_dash_state_paren_zip_shape():
    assert clean_location_for_parsing("Laredo-Texas(78043)") == "Laredo, Texas"
    assert clean_location_for_parsing("Dallas-Texas(75216)") == "Dallas, Texas"


def test_clean_dash_state_paren_zip_captures_multiword_city_whole():
    # The city segment is greedy-minimal up to the LAST dash, so a
    # multi-word city keeps its own internal space rather than being
    # split at it.
    assert (
        clean_location_for_parsing("College Station-Texas(77845)")
        == "College Station, Texas"
    )


def test_clean_dash_state_paren_zip_unaffected_by_other_dash_patterns():
    # Sanity: every other dash-joined shape in this file must be
    # completely untouched by adding this new, narrowly-scoped pattern.
    assert clean_location_for_parsing("DE - Berlin, Germany") == "Berlin, Germany"
    assert clean_location_for_parsing("Idaho - Boise") == "Boise, Idaho"
    assert (
        clean_location_for_parsing("Winston- Salem, NC - USA") == "Winston- Salem, NC"
    )




# --- Leading regional-org prefix ("AMER - <Country> - <Region-or-City> -
# --- [<City-or-suffix>]") — a sales-region-grouping ATS convention with
# --- no comma anywhere in the string (2026-09-20). ---


def test_clean_org_region_prefix_reorders_trailing_city():
    assert (
        clean_location_for_parsing("AMER - Canada - Alberta - Calgary - 8th Street NE")
        == "Calgary, Canada"
    )
    assert (
        clean_location_for_parsing("AMER - United States - Georgia - Atlanta - Peachtree St NW")
        == "Atlanta, United States"
    )
    assert clean_location_for_parsing("APAC - India - New Delhi") == "New Delhi, India"


def test_clean_org_region_prefix_drops_noise_only_suffix():
    assert (
        clean_location_for_parsing("AMER - United States - Alabama - Offsite/Home")
        == "Alabama, United States"
    )
    # No real city segment survives once the noise suffix is dropped — left
    # as the bare country name, same "no city to extract" outcome as any
    # other country-only string.
    assert clean_location_for_parsing("EMEA - United Kingdom - Remote") == "United Kingdom"


def test_clean_org_region_prefix_handles_no_space_around_dash():
    assert clean_location_for_parsing("EMEA-NL-NH-Amsterdam") == "Amsterdam, NL"


def test_clean_org_region_prefix_only_recognizes_english_street_suffixes():
    # Known, accepted limitation: _looks_like_street_address only matches
    # English street-suffix words ("street", "st", "avenue", ...), same
    # scope as every other street-address regex in this file. A trailing
    # segment in another language ("Balanstrasse" — German for "street")
    # isn't recognized as an address, so it's kept as the (wrong) city
    # instead of the real one before it ("Munich") — an accepted miss, not
    # a guess, matching this file's existing English-only street-suffix
    # scope elsewhere.
    assert clean_location_for_parsing("EMEA - Germany - Munich - Balanstrasse") == "Balanstrasse, Germany"
