from scraper.location_resolver import (
    _clean_location_for_parsing,
    parse_location,
    resolve_country_from_location,
)


def test_resolve_country_city_state_us():
    assert resolve_country_from_location("San Francisco, CA") == "US"


def test_resolve_country_uk_alias():
    assert resolve_country_from_location("London, UK") == "GB"


def test_resolve_country_parenthetical():
    assert resolve_country_from_location("Remote (US)") == "US"


def test_resolve_country_full_name_substring():
    assert resolve_country_from_location("Berlin, Germany, Hybrid") == "DE"


def test_resolve_country_usa_alias():
    assert resolve_country_from_location("USA") == "US"


def test_resolve_country_canadian_province_abbreviation():
    assert resolve_country_from_location("Toronto, ON") == "CA"


def test_resolve_country_none_when_ambiguous():
    assert resolve_country_from_location("Remote") is None


def test_resolve_country_city_name_collides_with_other_country_state_token():
    # "Ontario" is a CA province token but also a real US city (in
    # California); "Yukon" is a CA province token but also a real US city
    # (in Oklahoma). The trailing token is the true jurisdiction in both —
    # must not misclassify these as CA just because a CA province token
    # appears earlier in the string as a city name.
    assert resolve_country_from_location("Ontario, California") == "US"
    assert resolve_country_from_location("Yukon, Oklahoma") == "US"


def test_resolve_country_still_correct_without_collision():
    # No competing token from the other country — first/only match still
    # wins, same as before this collision guard existed.
    assert resolve_country_from_location("Toronto, Ontario, Canada") == "CA"
    assert resolve_country_from_location("Ontario, Canada") == "CA"


def test_resolve_country_none_when_empty():
    assert resolve_country_from_location("") is None
    assert resolve_country_from_location(None) is None


def test_resolve_country_never_false_positives_on_substring():
    # "us" inside "australia" must not match — word-boundary scan only.
    assert resolve_country_from_location("Sydney, Australia") == "AU"


def test_resolve_country_leading_iso_dot_shape():
    # Confirmed on AtkinsRéalis's SmartRecruiters feed: a dot-delimited
    # "<ISO2>.<City>.<Address>" path with no space after the leading code.
    assert resolve_country_from_location("HK.Harbour City.Gateway") == "HK"
    assert resolve_country_from_location("IN.Noida BPTP Capital City") == "IN"
    assert resolve_country_from_location("GB.Glasgow.2 Atlantic Square York Street") == "GB"
    assert resolve_country_from_location("CA.QC.Montréal.455 boul. René-Lévesque Ouest") == "CA"
    assert resolve_country_from_location("AU.South Australia") == "AU"


def test_resolve_country_leading_iso_dot_does_not_shadow_english_abbreviations():
    # "st"/"mt" are also valid ISO codes (São Tomé; n/a) but "St. "/"Mt. "
    # (abbreviation + space) must never be read as the dot-shape above —
    # only a same-vendor case with a space after its leading code
    # ("PE. Lima...") is an accepted miss, not one of these two.
    assert resolve_country_from_location("St. Louis, MO") == "US"
    assert resolve_country_from_location("Mt. Pleasant, SC") == "US"


def test_resolve_country_leading_iso3_dash_shape():
    # A second ATS vendor family: alpha-3 code + "-" instead of alpha-2 + ".",
    # both glued directly ("CAN-ON-Kitchener") and space-padded
    # ("BRA - Sao Paulo - Sao Paulo (Torre Z)").
    assert resolve_country_from_location("CAN-ON-Kitchener") == "CA"
    assert resolve_country_from_location("JPN-Tokyo-OVOL") == "JP"
    assert resolve_country_from_location("BRA - Sao Paulo - Sao Paulo (Torre Z)") == "BR"
    assert resolve_country_from_location("DEU - Berlin - Berlin") == "DE"
    assert resolve_country_from_location("VNM - Hanoi, Viet Nam") == "VN"
    # ROM is not the real ISO alpha-3 for Romania (ROU is) but is observed
    # vendor usage and unambiguous in context.
    assert resolve_country_from_location("ROM-Bucharest, PO") == "RO"


def test_resolve_country_leading_iso3_dash_rejects_non_codes():
    # "JGH"/"CPO" are 3 letters + dash but not real country codes — must
    # fall through to None, not guess.
    assert resolve_country_from_location("JGH - Jewish General Hosp.") is None
    assert resolve_country_from_location("CPO - Copenhagen Office") is None


def test_resolve_country_leading_iso2_region_dash_shape():
    # A third vendor family: "<ISO2>-<REGION>-<City>-..." with no spaces,
    # both segments ALL UPPERCASE (e.g. "CA-QC-LONGUEUIL-J01").
    assert (
        resolve_country_from_location("CA-QC-LONGUEUIL-J01 ~ 1000 Blvd Marie-Victorin ~ J01 BLDG")
        == "CA"
    )
    assert (
        resolve_country_from_location("AU-NSW-WILLIAMTOWN-001 ~ 1 Technology Pl ~ BLDG C, Unit 201")
        == "AU"
    )
    # Numeric region segment is also valid for this shape.
    assert resolve_country_from_location("PL-12-NIEPOLOMICE-004 ~ Grabska 4 ~ GRABSKA") == "PL"


def test_resolve_country_leading_iso2_region_dash_rejects_us_domestic_shape():
    # A same-shaped US-domestic vendor feed exists where the city segment is
    # mixed/lower case — that's California/Oregon/Texas, not
    # Canada/Oman/Thailand. All-caps-region is what distinguishes the two;
    # this must never resolve to the wrong country.
    assert resolve_country_from_location("CA-Fresno-cCARE Clinic") is None
    assert resolve_country_from_location("OR-Oregon-FIELD") is None
    assert resolve_country_from_location("TX-Austin-Nucl Pharm #56") is None


def test_resolve_country_trailing_alpha3_shape():
    # "<City>, <ISO3>" — a bare 3-letter code the comma-tokenizer's
    # alias/name-table checks never matched before.
    assert resolve_country_from_location("Bengaluru, IND") == "IN"
    assert resolve_country_from_location("London, GBR") == "GB"
    assert resolve_country_from_location("Tokyo, JPN") == "JP"
    # Not a real code — must not guess.
    assert resolve_country_from_location("Stuttgart, GER") is None


def test_resolve_country_accented_province_name():
    # "québec" (accented) previously never matched CA_PROVINCE_TOKENS'
    # unaccented "quebec" entry.
    assert resolve_country_from_location("Montréal, Québec") == "CA"
    assert resolve_country_from_location("Sherbrooke, Québec") == "CA"


def test_resolve_country_trailing_state_with_period():
    # "Vancouver, BC." — a trailing period after the 2-letter province/state
    # token previously broke the trailing-state regex's end anchor.
    assert resolve_country_from_location("Vancouver, BC.") == "CA"


def test_parse_location_normalized_key_folds_case_and_whitespace():
    a = parse_location("Toronto, Ontario, Canada")
    b = parse_location("TORONTO, Ontario, Canada")
    c = parse_location("  Toronto, Ontario, Canada  ")
    assert a.normalized_key == b.normalized_key == c.normalized_key


def test_parse_location_distinct_cities_get_distinct_keys():
    a = parse_location("Toronto, Ontario, Canada")
    b = parse_location("Vancouver, British Columbia, Canada")
    assert a.normalized_key != b.normalized_key


def test_parse_location_is_remote_flag():
    assert parse_location("Remote (US)").is_remote is True
    assert parse_location("San Francisco, CA").is_remote is False


def test_parse_location_country_code_populated():
    parsed = parse_location("San Francisco, CA")
    assert parsed.country_code == "US"


def test_parse_location_city_extracted_when_first_token_is_a_place():
    parsed = parse_location("Toronto, Ontario, Canada")
    assert parsed.city == "Toronto"


def test_parse_location_no_city_when_first_token_is_country_or_remote():
    assert parse_location("Canada").city is None
    assert parse_location("Remote").city is None


def test_parse_location_region_extracted_for_us_state():
    parsed = parse_location("San Francisco, CA, United States")
    assert parsed.region == "CA"


def test_parse_location_preserves_raw_string():
    parsed = parse_location("  Spain Remote  ")
    assert parsed.raw == "  Spain Remote  "


def test_parse_location_region_extracted_for_bare_city_state_shape():
    # A plain 2-token "City, ST" string must extract the trailing token as
    # region — this used to silently read tokens[-2] (== tokens[0], the
    # city) instead of the true trailing state/province token.
    parsed = parse_location("Toronto, ON")
    assert parsed.city == "Toronto"
    assert parsed.region == "ON"


def test_parse_location_region_not_the_city_token_itself():
    # A 2-token string whose first token is NOT a state/province must not
    # get that same token echoed back as region.
    parsed = parse_location("Berlin, DE")
    assert parsed.region != "Berlin"


def test_parse_location_region_suppressed_when_country_resolves_elsewhere():
    # "NSW" isn't a US/CA state/province token, so this mainly documents the
    # general contract: region extraction only fires when country_code
    # actually resolved to US or CA — a location whose country resolves
    # elsewhere (here, via the full "Australia" name, a higher-priority
    # match than any trailing-token heuristic) never gets a region guessed
    # from US/CA tables.
    parsed = parse_location("Sydney, NSW, Australia")
    assert parsed.country_code == "AU"
    assert parsed.region is None


def test_parse_location_region_consistent_with_resolved_country():
    # Many US-state/CA-province 2-letter tokens double as real ISO country
    # codes ("DE" Delaware/Germany, "IN" Indiana/India) — resolve_country_
    # from_location() already has to pick a reading for these (it
    # prioritizes the US/CA state reading, a separate pre-existing trade-off
    # this test isn't about). What this test guards: region extraction must
    # never disagree with that call — it either agrees (both say US/CA) or
    # region stays None, never a scoping value for a country other than
    # whatever country_code itself already settled on.
    for raw in ("Berlin, DE", "Bangalore, IN"):
        parsed = parse_location(raw)
        if parsed.region is not None:
            assert parsed.country_code in ("US", "CA")


def test_parse_location_city_extracted_despite_state_name_collision():
    # "New York" is both a real city and a full US state name. A distinct
    # state abbreviation elsewhere in the string ("NY") disambiguates it as
    # the city being named, not the state.
    parsed = parse_location("New York, NY")
    assert parsed.city == "New York"
    assert parsed.region == "NY"


def test_parse_location_state_name_alone_still_not_a_city():
    # Without a distinct disambiguating token, a bare state/province name
    # must still NOT be read as a city (no regression from the collision fix).
    assert parse_location("California, USA").city is None
    assert parse_location("Ontario, Canada").city is None


def test_parse_location_ambiguous_repeated_state_name_stays_unresolved():
    # Both tokens are literally the same state name — no distinct second
    # token exists to disambiguate, so city correctly stays unset.
    assert parse_location("New York, New York").city is None


def test_resolve_country_bare_city_name():
    # A location with no country/province/ISO signal at all — resolved via
    # _BARE_CITY_NAME_TO_COUNTRY, the gazetteer-derived lowest-priority
    # fallback tier.
    assert resolve_country_from_location("Mumbai") == "IN"
    assert resolve_country_from_location("Shanghai") == "CN"
    # Case-insensitive, matching the function's overall lowercasing.
    assert resolve_country_from_location("MUMBAI") == "IN"


def test_resolve_country_bare_city_name_excludes_known_false_positives():
    # "apac"/"federal" each have exactly one gazetteer match (a real but
    # obscure town) but were deliberately excluded as unsafe to trust bare —
    # confirms they were left out on purpose, not missed.
    assert resolve_country_from_location("APAC") is None
    assert resolve_country_from_location("Federal") is None


def test_resolve_country_bare_city_name_is_whole_string_only():
    # Must not fire on a city name embedded in a longer string — that's a
    # different signal (or lack thereof), not the bare-name fallback's job.
    assert resolve_country_from_location("Mumbai Office") is None
    # Already resolves via the name-matching tier before ever reaching the
    # bare-city fallback.
    assert resolve_country_from_location("Mumbai, India") == "IN"


def test_resolve_country_bare_city_name_second_expansion():
    # Re-derived against prod's actual unresolved-location strings (2026-09)
    # — same single-country-match method as the original table, just a
    # second pass against fresh data.
    assert resolve_country_from_location("Chicago") == "US"
    assert resolve_country_from_location("Kyiv") == "UA"
    assert resolve_country_from_location("South San Francisco") == "US"


def test_resolve_country_bare_city_name_excludes_names_ambiguous_in_cities1000():
    # These were valid single-country entries when _BARE_CITY_NAME_TO_COUNTRY
    # was derived against the smaller cities15000 gazetteer, but the
    # 2026-09-19 upgrade to cities1000 (~171k rows, see gazetteer.py) made
    # them genuinely ambiguous (e.g. "Toronto" now also matches small towns
    # in the US and Australia) — re-validated and removed rather than left
    # to silently guess wrong. Regression coverage so a future gazetteer
    # refresh doesn't quietly reintroduce them without the same check.
    assert resolve_country_from_location("Montreal") is None
    assert resolve_country_from_location("Toronto") is None
    assert resolve_country_from_location("Berlin") is None
    assert resolve_country_from_location("Prague") is None
    assert resolve_country_from_location("Dubai") is None
    assert resolve_country_from_location("Houston") is None
    # Still resolve correctly via the name-matching tier, which isn't
    # affected by _BARE_CITY_NAME_TO_COUNTRY's shrink at all.
    assert resolve_country_from_location("Montreal, Canada") == "CA"
    assert resolve_country_from_location("Toronto, ON") == "CA"


def test_resolve_country_bare_city_name_excludes_genuine_ambiguity():
    # These have more than one country match in the gazetteer (confirmed via
    # the same derivation script) — must stay None rather than guess, even
    # though they're common, well-known city names.
    assert resolve_country_from_location("San Francisco") is None  # US/AR/PH/CR/SV
    assert resolve_country_from_location("Ottawa") is None  # CA/US
    assert resolve_country_from_location("Hyderabad") is None  # IN/PK
    assert resolve_country_from_location("London") is None  # CA/GB


# --- Preprocessing cleanup (street address / store ID / trailing ZIP / --
# --- broader remote detection), sampled from real unresolved prod rows ---


def test_clean_strips_leading_street_address_before_city():
    assert (
        _clean_location_for_parsing("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
        == "Fullerton,CA"
    )
    assert (
        _clean_location_for_parsing("8680 Beechmont Ave, Cincinnati,OH 45255-4710")
        == "Cincinnati,OH"
    )


def test_clean_strips_store_id_prefix():
    # Also picks up the trailing-space-state comma insertion below, since
    # both the store-ID prefix and the missing city/state comma are
    # present in these real sampled strings.
    assert _clean_location_for_parsing("Store 2743142 Murrysville PA") == "Murrysville, PA"
    assert _clean_location_for_parsing("Store0187 Lexington KY") == "Lexington, KY"


def test_clean_strips_trailing_zip():
    assert _clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"
    assert _clean_location_for_parsing("Athens, GA, US, 30606") == "Athens, GA, US"


def test_clean_is_a_noop_when_nothing_matches():
    for s in ("Toronto, ON", "Remote", "Berlin, Germany", "Mt Laurel"):
        assert _clean_location_for_parsing(s) == s


def test_clean_never_returns_empty_string():
    # A pathological input that is entirely consumed by the street-address
    # pattern must fall back to the original raw string, never "" — an
    # empty city-extraction input is worse than the noisy original.
    assert _clean_location_for_parsing("123 Main Street") == "123 Main Street"


def test_parse_location_resolves_city_state_country_past_street_address():
    parsed = parse_location("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
    assert parsed.city == "Fullerton"
    assert parsed.region == "CA"
    assert parsed.country_code == "US"


def test_parse_location_resolves_city_state_past_trailing_zip():
    parsed = parse_location("Athens, GA, US, 30606")
    assert parsed.city == "Athens"
    assert parsed.region == "GA"
    assert parsed.country_code == "US"


def test_parse_location_normalized_key_uses_untouched_raw_not_cleaned():
    # normalized_key is row identity (get_or_create_locations) and must
    # never be derived from the cleaned string — two differently-formatted
    # scrapes of the same real address must not silently collapse (or
    # split) based on what the cleaning patterns happen to strip.
    parsed = parse_location("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
    assert "200 w orangethorpe ave" in parsed.normalized_key
    assert parsed.raw == "200 W Orangethorpe Ave, Fullerton,CA 92832-2900"


def test_parse_location_is_remote_flag_covers_work_at_home_and_virtual():
    # These never contain the literal word "remote" but are real ATS
    # shapes for fully-remote postings — sampled from live pool data where
    # they were previously parsed with is_remote left False.
    assert parse_location("Work at Home - Nevada").is_remote is True
    assert parse_location("US Remote - DC").is_remote is True
    assert parse_location("Virtual, DNK").is_remote is True
    assert parse_location("San Francisco, CA").is_remote is False


# --- Trailing space-joined state/province ("Portland OR", store-ID-prefixed --
# --- "Store 2743142 Murrysville PA") — comma insertion ahead of parsing ---


def test_clean_inserts_comma_before_trailing_us_state_abbreviation():
    assert _clean_location_for_parsing("Portland OR") == "Portland, OR"
    assert _clean_location_for_parsing("Appleton WI") == "Appleton, WI"


def test_clean_inserts_comma_before_trailing_ca_province_abbreviation():
    assert _clean_location_for_parsing("Store 6000275 Montréal QC") == "Montréal, QC"


def test_clean_trailing_space_state_requires_all_caps():
    # Lowercase/mixed-case two-letter trailing words are common English,
    # not state codes ("in", "or", "hi") — must not fire on these, or a
    # huge share of ordinary sentences would get a spurious state region.
    assert _clean_location_for_parsing("Now Hiring in") == "Now Hiring in"
    assert _clean_location_for_parsing("Party time hi") == "Party time hi"


def test_clean_trailing_space_state_skipped_when_string_already_has_a_comma():
    # A string that already uses commas has its own, already-correct
    # tokenization (parse_location's tokens[-1]/tokens[-2] region logic) —
    # inserting a second comma here could only ever double up or conflict
    # with that, never help it.
    assert _clean_location_for_parsing("Toronto, ON") == "Toronto, ON"


def test_parse_location_resolves_city_and_region_for_space_joined_store_id():
    parsed = parse_location("Store 2743142 Murrysville PA")
    assert parsed.city == "Murrysville"
    assert parsed.region == "PA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Store0187 Lexington KY")
    assert parsed2.city == "Lexington"
    assert parsed2.region == "KY"
    assert parsed2.country_code == "US"


# --- City names that collide with a country name ("Lebanon, TN", "Jordan, --
# --- MN", "Mexico, ME") — extends the existing US-state/CA-province ---
# --- name-collision guard to _ISO_NAME_TO_CODE/LOCATION_ALIASES ---


def test_parse_location_city_extracted_despite_country_name_collision():
    # "Lebanon" alone is the country (LB); with a trailing US state token
    # as independent confirmation, it must read as the Tennessee city
    # instead — same principle as the existing state/province name
    # collision guard ("Washington, DC" / "New York, NY"), just triggered
    # by a country-name collision instead of a state-name one.
    parsed = parse_location("Lebanon, TN, US")
    assert parsed.city == "Lebanon"
    assert parsed.region == "TN"
    assert parsed.country_code == "US"


def test_parse_location_city_extracted_despite_country_name_collision_more_cases():
    assert parse_location("Jordan, MN").city == "Jordan"
    assert parse_location("Mexico, ME").city == "Mexico"
    assert parse_location("Chile, WI").city == "Chile"
    assert parse_location("Panama, NY").city == "Panama"


def test_parse_location_bare_country_name_still_has_no_city():
    # No state/province token anywhere in the string — must stay the
    # conservative "this is the country, not a city" reading.
    parsed = parse_location("Lebanon")
    assert parsed.city is None
    assert parsed.country_code == "LB"


def test_parse_location_real_country_usage_unaffected_by_collision_guard():
    # "Beirut, Lebanon" has no US-state/CA-province token anywhere, so the
    # guard must never fire here — Lebanon stays the country, not a
    # phantom US-city reading.
    parsed = parse_location("Beirut, Lebanon")
    assert parsed.city == "Beirut"
    assert parsed.country_code == "LB"


# --- Canadian addresses with a trailing "CA" (ISO code) after a real CA --
# --- province token ("London, ON, CA, N6E 1V4") — previously misread as --
# --- California, since a bare "ca" token also matches US_STATE_TOKENS ---


def test_clean_strips_trailing_canadian_postal_code():
    assert _clean_location_for_parsing("London, ON, CA, N6E 1V4") == "London, ON, CA"
    assert _clean_location_for_parsing("Montreal, QC, CA, H3B4G7") == "Montreal, QC, CA"
    assert _clean_location_for_parsing("Milton, ON, CA, L9T 0A5") == "Milton, ON, CA"


def test_resolve_country_trailing_ca_after_province_is_canada_not_california():
    assert resolve_country_from_location("London, ON, CA") == "CA"
    assert resolve_country_from_location("Lethbridge, AB, CA") == "CA"


def test_resolve_country_bare_trailing_ca_still_california():
    # No distinct CA-province token before it — must stay the ordinary,
    # overwhelmingly common California reading. The new tier only fires
    # for the specific "<province>, ca" last-two-tokens shape.
    assert resolve_country_from_location("San Francisco, CA") == "US"
    assert resolve_country_from_location("Capitola, CA, United States") == "US"


def test_parse_location_resolves_canadian_address_past_postal_code():
    parsed = parse_location("London, ON, CA, N6E 1V4")
    assert parsed.city == "London"
    assert parsed.region == "ON"
    assert parsed.country_code == "CA"


def test_parse_location_california_address_unaffected_by_ca_canada_fix():
    parsed = parse_location("Marina Del Rey, CA, US, 90202")
    assert parsed.city == "Marina Del Rey"
    assert parsed.region == "CA"
    assert parsed.country_code == "US"


# --- Leading "<ST> - <City>" / "<ST>-<City>" ("WV - Triadelphia, 215 --
# --- Cabela Dr", "CT-WALLINGFORD, 108 LEIGUS RD") — a documented, --
# --- deliberately unhandled ambiguity in resolve_country_from_location's --
# --- own ISO2-region-dash tier (see _LEADING_ISO2_REGION_DASH_RE) ---


def test_clean_reorders_leading_state_dash_to_trailing_comma_shape():
    assert (
        _clean_location_for_parsing("WV - Triadelphia, 215 Cabela Dr - Retail XFR2716")
        == "Triadelphia, WV, 215 Cabela Dr - Retail XFR2716"
    )
    assert _clean_location_for_parsing("WA - Fife") == "Fife, WA"
    assert (
        _clean_location_for_parsing("CT-WALLINGFORD, 108 LEIGUS RD, 1ST FL")
        == "WALLINGFORD, CT, 108 LEIGUS RD, 1ST FL"
    )


def test_clean_leading_state_dash_skips_the_iso2_region_dash_ats_shape():
    # "CA-QC-LONGUEUIL-J01" / "AU-NSW-WILLIAMTOWN-001" are the OTHER
    # documented leading-dash shape (all-caps ISO2 country + region code),
    # already handled correctly and more precisely by
    # _LEADING_ISO2_REGION_DASH_RE inside resolve_country_from_location —
    # must be left untouched, not reordered as if "CA"/"AU" were a US
    # state/CA province.
    assert _clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"
    assert _clean_location_for_parsing("AU-NSW-WILLIAMTOWN-001") == "AU-NSW-WILLIAMTOWN-001"


def test_parse_location_resolves_leading_state_dash_shape():
    parsed = parse_location("WV - Triadelphia, 215 Cabela Dr - Retail XFR2716")
    assert parsed.city == "Triadelphia"
    assert parsed.region == "WV"
    assert parsed.country_code == "US"

    parsed2 = parse_location("PA - Harrisburg, 4601 Smith St")
    assert parsed2.city == "Harrisburg"
    assert parsed2.region == "PA"
    assert parsed2.country_code == "US"


def test_parse_location_iso2_region_dash_shape_still_resolves_country():
    # Country resolution for this shape must be exactly as it was before
    # the leading-state-dash cleanup existed.
    assert parse_location("CA-QC-LONGUEUIL-J01").country_code == "CA"
    assert parse_location("AU-NSW-WILLIAMTOWN-001").country_code == "AU"


# --- Trailing short (1-4 digit) facility code after the state, space- --
# --- separated ("Fayetteville, NC 0388") — same failure mode as the --
# --- 5-digit ZIP case, just a shorter code ---


def test_clean_strips_trailing_short_facility_code():
    assert _clean_location_for_parsing("Fayetteville, NC 0388") == "Fayetteville, NC"
    assert _clean_location_for_parsing("Kahului, HI 3279") == "Kahului, HI"
    assert _clean_location_for_parsing("Fremont, OH 0019") == "Fremont, OH"


def test_clean_trailing_short_code_does_not_touch_5_digit_zip():
    # 5-digit is _TRAILING_ZIP_RE's job (runs first) — must not double
    # apply or disagree on the boundary.
    assert _clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"


def test_parse_location_resolves_city_and_region_past_short_trailing_code():
    parsed = parse_location("Fayetteville, NC 0388")
    assert parsed.city == "Fayetteville"
    assert parsed.region == "NC"
    assert parsed.country_code == "US"


# --- Trailing digits stuck after a closing paren ("W. Jefferson, NC (W --
# --- Jefferson) 2255") — breaks the state-token match once parens strip ---


def test_clean_strips_trailing_digits_after_paren():
    assert (
        _clean_location_for_parsing("W. Jefferson, NC (W Jefferson) 2255")
        == "W. Jefferson, NC (W Jefferson)"
    )
    assert (
        _clean_location_for_parsing("Chandler, AZ (W Chandler) 0674")
        == "Chandler, AZ (W Chandler)"
    )


def test_parse_location_resolves_region_past_trailing_paren_code():
    parsed = parse_location("Warwick, RI (N Warwick) 2397")
    assert parsed.city == "Warwick"
    assert parsed.region == "RI"
    assert parsed.country_code == "US"


# --- Trailing "STORE - NNNN" suffix, city-first ("QUINCY STORE - 1915") --
# --- — the mirror image of the leading store-ID-prefix case ---


def test_clean_strips_trailing_store_suffix():
    assert _clean_location_for_parsing("QUINCY STORE - 1915") == "QUINCY"
    assert _clean_location_for_parsing("PICKERING STORE - 7238") == "PICKERING"


def test_parse_location_resolves_city_from_trailing_store_suffix():
    parsed = parse_location("HALIFAX STORE - 7126")
    assert parsed.city == "HALIFAX"


# --- "<ST>, <City>, ..." — reversed comma order from the far more common --
# --- "<City>, <ST>" shape ("TX, Austin, 11501 Alterra Pkwy STE 500") ---


def test_parse_location_extracts_city_from_reversed_state_first_order():
    parsed = parse_location("NJ, Morris Plains, 115 Tabor Rd")
    assert parsed.city == "Morris Plains"
    assert parsed.region == "NJ"
    assert parsed.country_code == "US"

    parsed2 = parse_location("TX, Austin, 11501 Alterra Pkwy STE 500")
    assert parsed2.city == "Austin"
    assert parsed2.region == "TX"
    assert parsed2.country_code == "US"


def test_parse_location_reversed_order_ca_province_too():
    parsed = parse_location("ON, Toronto, 123 King St")
    assert parsed.city == "Toronto"
    assert parsed.region == "ON"
    assert parsed.country_code == "CA"


def test_parse_location_reversed_order_no_city_guessed_when_second_token_is_also_a_jurisdiction():
    # "<ST>, <ST2/Country>, ..." has no real city here — must not guess
    # tokens[1] as a city just because it follows a state token.
    parsed = parse_location("WV, United States")
    assert parsed.city is None
    assert parsed.country_code == "US"

    parsed2 = parse_location("DC, DC, United States")
    assert parsed2.city is None


def test_parse_location_normal_city_first_order_unaffected_by_reversed_order_fix():
    # The far more common "<City>, <ST>" order must be completely
    # untouched by adding support for the reversed order.
    parsed = parse_location("Austin, TX")
    assert parsed.city == "Austin"
    assert parsed.region == "TX"
    assert parsed.country_code == "US"


# --- Leading full state/province name + dash ("Idaho - Boise", "Kansas --
# --- - Great Bend") — full-name variant of the 2-letter-code case ---


def test_clean_reorders_leading_full_state_name_dash():
    assert _clean_location_for_parsing("Idaho - Boise") == "Boise, Idaho"
    assert _clean_location_for_parsing("Kansas - Great Bend") == "Great Bend, Kansas"


def test_clean_leading_full_state_name_dash_skips_remote_and_work_at_home():
    # "remote"/"work at home" are not state/province names — must not
    # fire just because they precede a dash.
    assert _clean_location_for_parsing("Remote - Toronto") == "Remote - Toronto"
    assert _clean_location_for_parsing("Work at Home - Nevada") == "Work at Home - Nevada"


def test_clean_leading_full_state_name_dash_skips_iso2_region_dash_shape():
    # Must not compete with the 2-letter-code branch's own ISO2-region-
    # dash guard — "CA" is also a US_STATE_TOKENS member (California), so
    # without this guard the full-name branch would wrongly reorder
    # "CA-QC-LONGUEUIL-J01" too.
    assert _clean_location_for_parsing("CA-QC-LONGUEUIL-J01") == "CA-QC-LONGUEUIL-J01"


def test_parse_location_resolves_leading_full_state_name_dash():
    parsed = parse_location("Idaho - Boise")
    assert parsed.city == "Boise"
    assert parsed.region == "Idaho"
    assert parsed.country_code == "US"


# --- Leading zero-padded 5-digit facility ID + dash ("02319 - Grove --
# --- City Dialysis") — different vendor convention from "Store <id>" ---


def test_clean_strips_leading_5_digit_facility_id():
    assert _clean_location_for_parsing("02319 - Grove City Dialysis") == "Grove City Dialysis"
    assert _clean_location_for_parsing("11722 - Majestic Dialysis") == "Majestic Dialysis"


def test_parse_location_city_recovers_past_leading_facility_id():
    # Brand-word suffix ("Dialysis") is deliberately left in city — not
    # safely separable from a real multi-word city name without guessing.
    parsed = parse_location("05252 - Two Rivers Dialysis")
    assert parsed.city == "Two Rivers Dialysis"


# --- Bare, unambiguous ISO alpha-2 country codes ("GB", "FR", "CN", --
# --- "AU" alone, or "GB,Manchester" with no space after the comma) — --
# --- previously fell through to None everywhere in this file ---


def test_resolve_country_bare_alpha2_code():
    assert resolve_country_from_location("GB") == "GB"
    assert resolve_country_from_location("FR") == "FR"
    assert resolve_country_from_location("CN") == "CN"
    assert resolve_country_from_location("AU") == "AU"
    assert resolve_country_from_location("AM") == "AM"


def test_resolve_country_bare_alpha2_code_case_insensitive():
    assert resolve_country_from_location("gb") == "GB"


def test_resolve_country_bare_alpha2_excludes_us_ca_collision_codes():
    # "CA"/"DE"/"IN"/"MD"/... collide with a US state or CA province
    # abbreviation — must keep resolving via the existing, deliberate
    # state/province-wins-ties logic, never this newer, lower-priority
    # tier (which excludes them from its table entirely for exactly this
    # reason).
    assert resolve_country_from_location("CA") == "US"  # California, not Canada
    assert resolve_country_from_location("DE") == "US"  # Delaware, not Germany


def test_parse_location_extracts_city_past_leading_bare_alpha2_code():
    parsed = parse_location("GB,Manchester")
    assert parsed.city == "Manchester"
    assert parsed.country_code == "GB"

    parsed2 = parse_location("AM,Yerevan")
    assert parsed2.city == "Yerevan"
    assert parsed2.country_code == "AM"


def test_parse_location_bare_alpha2_no_city_guessed_when_second_token_is_also_non_city():
    parsed = parse_location("GB,Remote")
    assert parsed.city is None
    assert parsed.country_code == "GB"


def test_parse_location_bare_alpha2_does_not_set_region():
    # region elsewhere in this function only ever holds a US state/CA
    # province — a whole country from this tier must not populate it.
    parsed = parse_location("GB,Manchester")
    assert parsed.region is None


# --- Leading US-state/CA-province COLLISION code ("DE", "IN", "CA", --
# --- ...) with an explicit country name elsewhere in the string ---
# --- ("DE - Berlin, Germany") — a real correctness bug found while --
# --- investigating unmatched rows: the leading-dash reorder fixes --
# --- above moved the collision code into its own clean token, which --
# --- then won the wrong (US-state) reading ahead of the correct one --
# --- the unreordered string already produced ---


def test_resolve_country_prioritizes_explicit_country_name_over_leading_collision_code():
    # Without the fix, "DE - Berlin, Germany" resolved to "US" (Delaware)
    # — confirmed live before this fix, since resolve_country_from_
    # location on the RAW string already correctly returns "DE" here, but
    # the leading-dash cleanup was reordering it into a shape that broke
    # that correct reading.
    assert resolve_country_from_location("DE - Berlin, Germany") == "DE"
    assert resolve_country_from_location("IN - Mumbai, India") == "IN"
    assert resolve_country_from_location("CA - Toronto, Canada") == "CA"


def test_parse_location_prioritizes_explicit_country_name_over_leading_collision_code():
    parsed = parse_location("DE - Berlin, Germany")
    assert parsed.city == "Berlin"
    assert parsed.country_code == "DE"

    parsed2 = parse_location("DE - Munich, Germany")
    assert parsed2.city == "Munich"
    assert parsed2.country_code == "DE"


def test_parse_location_collision_code_without_explicit_country_still_resolves_via_city_region_table():
    # No "Germany" spelled out anywhere in these strings, but "Berlin"
    # itself is in _CITY_REGION_COLLISION_TO_COUNTRY (no real US town
    # named Berlin has admin1_code "DE" — the only real US Berlins are in
    # MD/NJ/PA/MA/NH/WI — so ("berlin", "de") was a safe, single-match
    # derivation). This is a stronger, data-validated signal than the
    # general state/province-wins-ties trade-off, so it overrides that
    # trade-off here even with no explicit country name present.
    parsed = parse_location("DE-Berlin")
    assert parsed.city == "Berlin"
    assert parsed.country_code == "DE"

    parsed2 = parse_location("Berlin, DE")
    assert parsed2.country_code == "DE"


def test_parse_location_bare_collision_code_still_keeps_existing_trade_off():
    # No city at all — _CITY_REGION_COLLISION_TO_COUNTRY has nothing to
    # key on here, so the original, documented state/province-wins-ties
    # trade-off must still apply exactly as before.
    assert parse_location("DE").country_code == "US"
    assert parse_location("IN").country_code == "US"


def test_clean_leading_word_dash_still_works_for_non_colliding_states():
    # Sanity: "WV - Triadelphia..."/"Idaho - Boise" have no country-name
    # collision risk at all (WV/Idaho aren't ISO country codes) — must be
    # completely unaffected by this fix.
    assert parse_location("WV - Triadelphia, 215 Cabela Dr").city == "Triadelphia"
    assert parse_location("Idaho - Boise").city == "Boise"


# --- _CITY_REGION_COLLISION_TO_COUNTRY — data-derived (city, collision- --
# --- code) pairs where no real US/CA town of that name exists in that --
# --- state/province, found while investigating gazetteer-match --
# --- failures for cities like "Bangalore, IN" (resolving to Indiana --
# --- instead of India) ---


def test_parse_location_city_region_table_corrects_india_cities():
    for city in ("Bangalore", "Chennai", "Mumbai", "Hyderabad", "Pune"):
        parsed = parse_location(f"{city}, IN")
        assert parsed.country_code == "IN", city
        assert parsed.region is None, city


def test_parse_location_city_region_table_corrects_germany_cities():
    for city in ("Berlin", "Munich", "Hamburg", "Frankfurt am Main"):
        parsed = parse_location(f"{city}, DE")
        assert parsed.country_code == "DE", city


def test_parse_location_city_region_table_leaves_real_us_towns_alone():
    # These ARE real US towns in exactly the state shown — the table's
    # own derivation excludes any (city, collision_code) pair where a
    # matching US admin1 town exists, so these must be completely
    # unaffected.
    for city, state in (
        ("Earth City", "MO"),
        ("Henrico", "VA"),
        ("Geismar", "LA"),
        ("Arden", "NC"),
    ):
        parsed = parse_location(f"{city}, {state}")
        assert parsed.country_code == "US", city
        assert parsed.region == state, city


def test_parse_location_city_region_table_only_applies_when_country_already_us_or_ca():
    # Defensive: the correction must never fire when country_code resolved
    # to something else entirely (nothing in this table's design should
    # let that happen, but this locks the guard in explicitly).
    parsed = parse_location("Bangalore, Karnataka, India")
    assert parsed.country_code == "IN"


# --- Trailing "<ST> - <suffix>" after the state token ("Dallas, TX - --
# --- USA", "New Haven, CT - USA") — found while investigating why huge --
# --- cities like Dallas/Amsterdam/Shanghai weren't matching the --
# --- gazetteer: the dash-glued suffix broke tokens[-1]'s state match, --
# --- so region stayed None and town_resolver.py correctly refused to --
# --- guess among multiple same-named US towns without it ---


def test_clean_strips_trailing_state_dash_suffix():
    assert _clean_location_for_parsing("Dallas, TX - USA") == "Dallas, TX"
    assert _clean_location_for_parsing("Dallas, TX - Data Center") == "Dallas, TX"
    assert _clean_location_for_parsing("New Haven, CT - USA") == "New Haven, CT"


def test_clean_trailing_state_dash_suffix_preserves_city_internal_dash():
    # The city itself has a dash BEFORE the comma — only the segment
    # after the LAST comma is a candidate for stripping.
    assert (
        _clean_location_for_parsing("Winston- Salem, NC - USA") == "Winston- Salem, NC"
    )


def test_parse_location_resolves_dallas_past_trailing_state_dash_suffix():
    # Dallas alone is genuinely ambiguous among US towns (GA/NC/TX/PA/OR
    # all have one) — town_resolver.py correctly refuses to guess without
    # region, which is exactly what this fix recovers.
    parsed = parse_location("Dallas, TX - USA")
    assert parsed.city == "Dallas"
    assert parsed.region == "TX"
    assert parsed.country_code == "US"


def test_parse_location_is_remote_preserved_despite_trailing_state_dash_strip():
    # is_remote is checked against the RAW string specifically so this
    # cleanup step (which discards the "- Remote" suffix for region
    # extraction purposes) can never suppress the remote signal.
    parsed = parse_location("Atlanta, GA - Remote")
    assert parsed.city == "Atlanta"
    assert parsed.region == "GA"
    assert parsed.is_remote is True


# --- Explicit country name elsewhere in the string overrides the US/CA --
# --- collision tier's own guess — generalizes the earlier "DE - Berlin, --
# --- Germany" leading-dash-only fix to the (more common) comma- --
# --- separated shape, found via "Shanghai, SD, China" (SD = Shanghai's --
# --- own district code, not South Dakota) and "Amsterdam, NH, --
# --- Netherlands" (NH = New Hampshire, not a collision code itself, but --
# --- still wrong without this fix since a US-state hit alone used to --
# --- short-circuit before ever checking for "Netherlands") ---


def test_resolve_country_explicit_country_name_overrides_state_collision_token():
    assert resolve_country_from_location("Shanghai, SD, China") == "CN"
    assert resolve_country_from_location("Amsterdam, NH, Netherlands") == "NL"


def test_resolve_country_explicit_name_agreeing_with_state_tier_unaffected():
    # The common case: explicit name and the tier's own answer agree, so
    # nothing changes — this is what proves the fix is safe to apply
    # unconditionally rather than only for known collision codes.
    assert resolve_country_from_location("Toronto, ON, Canada") == "CA"
    assert resolve_country_from_location("San Francisco, CA, USA") == "US"
    assert resolve_country_from_location("San Francisco, CA, United States") == "US"


def test_resolve_country_no_explicit_name_keeps_existing_trailing_token_rule():
    # No third token spelling out a country — "NL" (Newfoundland and
    # Labrador) vs "NH" (New Hampshire) stays genuinely ambiguous between
    # US/CA, so the pre-existing "prefer the trailing hit" rule still
    # applies exactly as before.
    assert resolve_country_from_location("Amsterdam, NH, NL") == "CA"


def test_parse_location_ordinary_city_state_country_unaffected():
    # Sanity: the overwhelmingly common shapes with no ambiguity at all.
    parsed = parse_location("Dallas, TX")
    assert parsed.city == "Dallas"
    assert parsed.region == "TX"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Toronto, ON")
    assert parsed2.city == "Toronto"
    assert parsed2.region == "ON"
    assert parsed2.country_code == "CA"


# --- Accented city spelling ("München, DE") missing the --
# --- _CITY_REGION_COLLISION_TO_COUNTRY correction that its ASCII- --
# --- folded/German-transliterated spellings ("munich"/"muenchen") --
# --- already got — found while investigating why huge cities kept --
# --- showing up unmatched despite fixes for their English spelling ---


def test_parse_location_city_region_table_lookup_folds_accents():
    parsed = parse_location("Düsseldorf, DE")
    assert parsed.country_code == "DE"


def test_parse_location_city_region_table_handles_munich_umlaut_spelling():
    # GeoNames has no "München"-named row for Munich at all (its primary
    # name is the English exonym "Munich"), so neither NFD accent-folding
    # ("munchen") nor the German "ue" transliteration ("muenchen") the
    # table's other entries use reach a real gazetteer match for this
    # exact spelling — a verified, hand-added table entry instead.
    parsed = parse_location("München, DE")
    assert parsed.city == "München"
    assert parsed.country_code == "DE"

    parsed2 = parse_location("Munich, DE")
    assert parsed2.country_code == "DE"


# --- Trailing 6-digit international postal code (India's PIN code, --
# --- Singapore's, Vietnam's, ...) — same failure mode as the 5-digit --
# --- US ZIP case, just a different digit count, found via "Bangalore, --
# --- Karnataka, IND, 560093" staying country_code=None even though --
# --- "IND" alone (no trailing digits) resolves fine ---


def test_clean_strips_trailing_6_digit_postal_code():
    assert (
        _clean_location_for_parsing("Bangalore, Karnataka, IND, 560093")
        == "Bangalore, Karnataka, IND"
    )
    assert _clean_location_for_parsing("Singapore, SG, 797546") == "Singapore, SG"


def test_clean_6_digit_postal_code_does_not_touch_5_digit_us_zip():
    assert _clean_location_for_parsing("Wayne, NJ, US, 07470") == "Wayne, NJ, US"
    assert _clean_location_for_parsing("Athens, GA, US, 30606") == "Athens, GA, US"


def test_parse_location_resolves_india_past_trailing_pin_code():
    parsed = parse_location("Bangalore, Karnataka, IND, 560093")
    assert parsed.city == "Bangalore"
    assert parsed.country_code == "IN"

    parsed2 = parse_location("Hyderabad, Telangana, IND, 500032")
    assert parsed2.city == "Hyderabad"
    assert parsed2.country_code == "IN"


def test_parse_location_resolves_other_countries_past_trailing_6_digit_code():
    assert parse_location("Singapore, SGP, 098633").country_code == "SG"
    assert parse_location("Tokyo, Tokyo, JPN, 530001").country_code == "JP"
    assert parse_location("Cluj-Napoca, ROU, 400604").country_code == "RO"


# --- "<CountryAlias>, <ST>, <City>" — 3-token, country-alias-first --
# --- ("USA, VA, McLean") — found while investigating why "USA"/"US"/ --
# --- "CAN" were the single most common garbage `city` values in the --
# --- unmatched pool: is_recognized_non_city correctly kept the alias --
# --- out of `city`, but nothing extracted the REAL city at tokens[2] ---


def test_parse_location_extracts_city_from_country_alias_first_order():
    parsed = parse_location("USA, VA, McLean")
    assert parsed.city == "McLean"
    assert parsed.region == "VA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("US, CO, Longmont")
    assert parsed2.city == "Longmont"
    assert parsed2.region == "CO"
    assert parsed2.country_code == "US"


def test_parse_location_extracts_city_from_alpha3_country_code_first_order():
    # "CAN"/"USA" as alpha-3 codes, not LOCATION_ALIASES entries — a
    # separate table (_ALPHA3_US_CA_TOKENS) had to recognize these too.
    parsed = parse_location("CAN, ON, London")
    assert parsed.city == "London"
    assert parsed.region == "ON"
    assert parsed.country_code == "CA"


def test_parse_location_country_alias_first_order_full_state_name():
    parsed = parse_location("US, New Mexico, Albuquerque")
    assert parsed.city == "Albuquerque"
    assert parsed.region == "New Mexico"
    assert parsed.country_code == "US"


def test_parse_location_country_alias_first_order_no_city_guessed_for_noise_phrases():
    # "Remote"/"Home Office" are the two overwhelmingly common non-city
    # trailing values in this shape — must not be guessed as a city.
    parsed = parse_location("USA, ID, Home Office")
    assert parsed.city is None
    assert parsed.region == "ID"
    assert parsed.country_code == "US"

    parsed2 = parse_location("USA, IA, Remote")
    assert parsed2.city is None
    assert parsed2.region == "IA"


def test_parse_location_country_alias_first_order_no_city_for_2_tokens():
    # No third token to be a city — must stay None, not guess.
    parsed = parse_location("USA, VA")
    assert parsed.city is None
    assert parsed.region == "VA"
    assert parsed.country_code == "US"


# --- LOCATION_ALIASES keys that are ALSO real US/CA town names --
# --- ("Holland, MI", "England, AR", "Scotland, SD", "Wales, WI") — --
# --- found via the same "USA, VA, McLean" investigation: "Holland, --
# --- MI" was resolving country_code="NL" instead of "US" ---


def test_resolve_country_ambiguous_alias_defers_to_real_us_ca_town():
    assert resolve_country_from_location("Holland, MI") == "US"
    assert resolve_country_from_location("England, AR") == "US"
    assert resolve_country_from_location("Scotland, SD") == "US"
    assert resolve_country_from_location("Wales, WI") == "US"


def test_resolve_country_ambiguous_alias_still_resolves_real_foreign_usage():
    assert resolve_country_from_location("London, UK") == "GB"
    assert resolve_country_from_location("Manchester, England") == "GB"
    assert resolve_country_from_location("Cardiff, Wales") == "GB"
    assert resolve_country_from_location("Amsterdam, Holland") == "NL"
    assert resolve_country_from_location("Holland") == "NL"


def test_resolve_country_non_ambiguous_aliases_unaffected():
    # "usa"/"uk"/"korea"/etc. are never real place names — must be
    # completely unaffected by the ambiguous-alias guard.
    assert resolve_country_from_location("USA") == "US"
    assert resolve_country_from_location("Seoul, South Korea") == "KR"


# --- Trailing compass-direction suffix on a street address ("7000 --
# --- Target Pkwy N", "15800 87th St NE") — the existing street-address --
# --- prefix strip left the direction letter as an opaque tokens[0], --
# --- leaking bare "N"/"NE"/"SW"/etc. into `city` ---


def test_clean_strips_street_address_with_direction_suffix():
    assert (
        _clean_location_for_parsing("15800 87th St NE, Otsego, MN 55330-6546")
        == "Otsego, MN"
    )
    assert (
        _clean_location_for_parsing("356 12th St SW, Forest Lake,MN 55025-1749")
        == "Forest Lake,MN"
    )


def test_clean_street_address_direction_suffix_all_eight_directions():
    for direction in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
        cleaned = _clean_location_for_parsing(f"100 Main St {direction}, Springfield, IL 62701")
        assert cleaned == "Springfield, IL", direction


def test_parse_location_resolves_city_past_direction_suffix_street_address():
    parsed = parse_location("3500 Marvin Rd NE, Lacey,WA 98516-1423")
    assert parsed.city == "Lacey"
    assert parsed.region == "WA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("7828 Georgia Ave NW, Washington,DC 20012-1305")
    assert parsed2.city == "Washington"
    assert parsed2.region == "DC"


def test_clean_street_address_without_direction_suffix_still_works():
    # Sanity: the original, more common shape with no direction suffix
    # at all must be completely unaffected.
    assert (
        _clean_location_for_parsing("200 W Orangethorpe Ave, Fullerton,CA 92832-2900")
        == "Fullerton,CA"
    )


# --- CA-province collision codes ("pe" Prince Edward Island/Peru, "nl" --
# --- Newfoundland and Labrador/Netherlands, "sk" Saskatchewan/ --
# --- Slovakia) — _CITY_REGION_COLLISION_TO_COUNTRY's original derivation --
# --- only covered US-collision codes; found via "Lima, LIM, PE, 15008" --
# --- resolving country_code="CA" instead of "PE" ---


def test_parse_location_city_region_table_covers_ca_province_collisions():
    assert parse_location("Lima, PE").country_code == "PE"
    assert parse_location("Amsterdam, NL").country_code == "NL"
    assert parse_location("Bratislava, SK").country_code == "SK"
    assert parse_location("Arequipa, PE").country_code == "PE"


def test_parse_location_city_region_table_fires_even_when_region_not_extracted():
    # "LIM" (tokens[-2]) isn't a recognized state/province token, so
    # region-extraction correctly leaves region=None here — but "pe" is
    # still present as a raw token, which the correction must scan for
    # directly rather than only ever consulting the extracted `region`.
    parsed = parse_location("Lima, LIM, PE, 15008")
    assert parsed.city == "Lima"
    assert parsed.country_code == "PE"

    parsed2 = parse_location("Lima, Callao Region, PE")
    assert parsed2.city == "Lima"
    assert parsed2.country_code == "PE"


def test_parse_location_city_region_table_ca_collision_leaves_real_ca_towns_alone():
    # A real Canadian town in a real matching province must stay CA.
    parsed = parse_location("Vernon, CA")
    assert parsed.country_code == "CA"


# --- "<Country>, <City>" — 2-token, full country NAME first ("Ireland, --
# --- Limerick", "India, Bangalore") — country_code already resolved --
# --- correctly via _ISO_NAME_TO_CODE, but nothing extracted tokens[1] --
# --- as the city this shape actually has (284 rows sampled) ---


def test_parse_location_extracts_city_from_country_name_first_order():
    for country_str, city in (
        ("Ireland", "Limerick"),
        ("India", "Bangalore"),
        ("Philippines", "Manila"),
        ("Netherlands", "Amsterdam"),
        ("China", "Shanghai"),
        ("Canada", "Vancouver"),
        ("Italy", "Milan"),
    ):
        parsed = parse_location(f"{country_str}, {city}")
        assert parsed.city == city, country_str
        assert parsed.region is None, country_str


def test_parse_location_country_name_first_order_no_city_for_noise_phrases():
    parsed = parse_location("Poland, Remote")
    assert parsed.city is None
    assert parsed.country_code == "PL"

    parsed2 = parse_location("United Kingdom, Home Office")
    assert parsed2.city is None
    assert parsed2.country_code == "GB"


def test_parse_location_country_name_first_order_no_city_for_bare_country():
    parsed = parse_location("Ireland")
    assert parsed.city is None
    assert parsed.country_code == "IE"


def test_parse_location_country_name_first_order_unaffected_by_city_name_collision_guard():
    # "Lebanon, TN"/"Jordan, MN" are the OTHER reading of a country-name-
    # first string — the existing collision guard already correctly reads
    # tokens[0] as the city itself (Lebanon TN, not the country Lebanon),
    # which sets is_recognized_non_city=False, so this new branch (gated
    # on is_recognized_non_city being True) must never fire for these.
    parsed = parse_location("Lebanon, TN")
    assert parsed.city == "Lebanon"
    assert parsed.country_code == "LB"

    parsed2 = parse_location("Jordan, MN")
    assert parsed2.city == "Jordan"
    assert parsed2.country_code == "JO"


# --- "<FullStateName> <remote-phrase>" — space-joined, no comma or dash --
# --- at all ("Utah Work at Home", "Oregon Virtual") — distinct from the --
# --- dash-joined "<ST> - Remote" shape already handled; 60 rows sampled ---


def test_clean_inserts_comma_before_trailing_remote_phrase():
    assert _clean_location_for_parsing("Utah Work at Home") == "Utah, Work at Home"
    assert _clean_location_for_parsing("Oregon Virtual") == "Oregon, Virtual"
    assert (
        _clean_location_for_parsing("West Virginia Work at Home")
        == "West Virginia, Work at Home"
    )


def test_parse_location_resolves_state_and_country_for_space_joined_remote_phrase():
    for state, phrase in (
        ("Utah", "Work at Home"),
        ("Tennessee", "Work at Home"),
        ("Oregon", "Virtual"),
        ("Delaware", "Virtual"),
        ("West Virginia", "Work at Home"),
        ("New Hampshire", "Virtual"),
    ):
        parsed = parse_location(f"{state} {phrase}")
        assert parsed.city is None, state
        assert parsed.region == state, state
        assert parsed.country_code == "US", state
        assert parsed.is_remote is True, state


def test_clean_remote_phrase_suffix_does_not_fire_on_non_state_leading_word():
    # No real state/province name before the remote phrase — must not
    # insert a comma or claim a region.
    assert _clean_location_for_parsing("Somewhere Remote") == "Somewhere Remote"


# --- region set independently of whether the second token turns out to --
# --- be a real city or a known non-city phrase — found via "Utah, Work --
# --- at Home" (after the comma-insertion fix above) leaving region=None --
# --- even though tokens[0]="utah" is an unambiguous, confirmed state ---


def test_parse_location_region_set_even_when_second_token_is_non_city_phrase():
    parsed = parse_location("USA, ID, Home Office")
    assert parsed.city is None
    assert parsed.region == "ID"
    assert parsed.country_code == "US"

    parsed2 = parse_location("AZ, US")
    assert parsed2.city is None
    assert parsed2.region == "AZ"
    assert parsed2.country_code == "US"


# --- "<City>-<FullStateName>(<zip>)" — no comma/space around the dash at --
# --- all, trailing zip in parens ("Laredo-Texas(78043)") — a distinct --
# --- ATS vendor shape from every other dash pattern (81 rows sampled) ---


def test_clean_reorders_dash_state_paren_zip_shape():
    assert _clean_location_for_parsing("Laredo-Texas(78043)") == "Laredo, Texas"
    assert _clean_location_for_parsing("Dallas-Texas(75216)") == "Dallas, Texas"


def test_clean_dash_state_paren_zip_captures_multiword_city_whole():
    # The city segment is greedy-minimal up to the LAST dash, so a
    # multi-word city keeps its own internal space rather than being
    # split at it.
    assert (
        _clean_location_for_parsing("College Station-Texas(77845)")
        == "College Station, Texas"
    )


def test_parse_location_resolves_dash_state_paren_zip_shape():
    parsed = parse_location("Laredo-Texas(78043)")
    assert parsed.city == "Laredo"
    assert parsed.region == "Texas"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Killeen-Texas(76548)")
    assert parsed2.city == "Killeen"
    assert parsed2.region == "Texas"
    assert parsed2.country_code == "US"


def test_clean_dash_state_paren_zip_unaffected_by_other_dash_patterns():
    # Sanity: every other dash-joined shape in this file must be
    # completely untouched by adding this new, narrowly-scoped pattern.
    assert _clean_location_for_parsing("DE - Berlin, Germany") == "Berlin, Germany"
    assert _clean_location_for_parsing("Idaho - Boise") == "Boise, Idaho"
    assert (
        _clean_location_for_parsing("Winston- Salem, NC - USA") == "Winston- Salem, NC"
    )
