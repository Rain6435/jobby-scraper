from scraper.location.cleaning import clean_location_for_parsing
from scraper.location.parse import parse_location


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


def test_clean_strips_trailing_canadian_postal_code():
    assert clean_location_for_parsing("London, ON, CA, N6E 1V4") == "London, ON, CA"
    assert clean_location_for_parsing("Montreal, QC, CA, H3B4G7") == "Montreal, QC, CA"
    assert clean_location_for_parsing("Milton, ON, CA, L9T 0A5") == "Milton, ON, CA"


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
    # _LEADING_ISO2_REGION_DASH_RE inside resolve_country_from_location —
    # must be left untouched, not reordered as if "CA"/"AU" were a US
    # state/CA province.
    assert clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"
    assert clean_location_for_parsing("AU-NSW-WILLIAMTOWN-001") == "AU-NSW-WILLIAMTOWN-001"


def test_clean_strips_trailing_short_facility_code():
    assert clean_location_for_parsing("Fayetteville, NC 0388") == "Fayetteville, NC"
    assert clean_location_for_parsing("Kahului, HI 3279") == "Kahului, HI"
    assert clean_location_for_parsing("Fremont, OH 0019") == "Fremont, OH"


def test_clean_trailing_short_code_does_not_touch_5_digit_zip():
    # 5-digit is _TRAILING_ZIP_RE's job (runs first) — must not double
    # apply or disagree on the boundary.
    assert clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"


def test_clean_strips_trailing_digits_after_paren():
    assert (
        clean_location_for_parsing("W. Jefferson, NC (W Jefferson) 2255")
        == "W. Jefferson, NC (W Jefferson)"
    )
    assert (
        clean_location_for_parsing("Chandler, AZ (W Chandler) 0674")
        == "Chandler, AZ (W Chandler)"
    )


def test_clean_strips_trailing_store_suffix():
    assert clean_location_for_parsing("QUINCY STORE - 1915") == "QUINCY"
    assert clean_location_for_parsing("PICKERING STORE - 7238") == "PICKERING"


def test_clean_reorders_leading_full_state_name_dash():
    assert clean_location_for_parsing("Idaho - Boise") == "Boise, Idaho"
    assert clean_location_for_parsing("Kansas - Great Bend") == "Great Bend, Kansas"


def test_clean_leading_full_state_name_dash_skips_remote_and_work_at_home():
    # "remote"/"work at home" are not state/province names — must not
    # fire just because they precede a dash.
    assert clean_location_for_parsing("Remote - Toronto") == "Remote - Toronto"
    assert clean_location_for_parsing("Work at Home - Nevada") == "Work at Home - Nevada"


def test_clean_leading_full_state_name_dash_skips_iso2_region_dash_shape():
    # Must not compete with the 2-letter-code branch's own ISO2-region-
    # dash guard — "CA" is also a US_STATE_TOKENS member (California), so
    # without this guard the full-name branch would wrongly reorder
    # "CA-QC-LONGUEUIL-J01" too.
    assert clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"


def test_clean_strips_leading_5_digit_facility_id():
    assert clean_location_for_parsing("02319 - Grove City Dialysis") == "Grove City Dialysis"
    assert clean_location_for_parsing("11722 - Majestic Dialysis") == "Majestic Dialysis"


def test_clean_leading_word_dash_still_works_for_non_colliding_states():
    # Sanity: "WV - Triadelphia..."/"Idaho - Boise" have no country-name
    # collision risk at all (WV/Idaho aren't ISO country codes) — must be
    # completely unaffected by this fix.
    assert parse_location("WV - Triadelphia, 215 Cabela Dr").city == "Triadelphia"
    assert parse_location("Idaho - Boise").city == "Boise"


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


def test_clean_strips_trailing_6_digit_postal_code():
    assert (
        clean_location_for_parsing("Bangalore, Karnataka, IND, 560093")
        == "Bangalore, Karnataka, IND"
    )
    assert clean_location_for_parsing("Singapore, SG, 797546") == "Singapore, SG"


def test_clean_6_digit_postal_code_does_not_touch_5_digit_us_zip():
    assert clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"
    assert clean_location_for_parsing("Athens, GA, US, 30606") == "Athens, GA, US"


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
