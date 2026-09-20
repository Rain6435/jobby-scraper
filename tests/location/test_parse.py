from scraper.location.parse import parse_location
from scraper.location_resolver import parse_location as parse_location_via_shim


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


def test_parse_location_preserves_raw_string_via_shim():
    # Guards the backward-compat shim (scraper/location_resolver.py) itself
    # against silent breakage — every other test in this file imports
    # parse_location directly from scraper.location.parse.
    parsed = parse_location_via_shim("  Spain Remote  ")
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


def test_parse_location_resolves_city_and_region_for_space_joined_store_id():
    parsed = parse_location("Store 2743142 Murrysville PA")
    assert parsed.city == "Murrysville"
    assert parsed.region == "PA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Store0187 Lexington KY")
    assert parsed2.city == "Lexington"
    assert parsed2.region == "KY"
    assert parsed2.country_code == "US"


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


def test_parse_location_resolves_city_and_region_past_short_trailing_code():
    parsed = parse_location("Fayetteville, NC 0388")
    assert parsed.city == "Fayetteville"
    assert parsed.region == "NC"
    assert parsed.country_code == "US"


def test_parse_location_resolves_region_past_trailing_paren_code():
    parsed = parse_location("Warwick, RI (N Warwick) 2397")
    assert parsed.city == "Warwick"
    assert parsed.region == "RI"
    assert parsed.country_code == "US"


def test_parse_location_resolves_city_from_trailing_store_suffix():
    parsed = parse_location("HALIFAX STORE - 7126")
    assert parsed.city == "HALIFAX"


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


def test_parse_location_resolves_leading_full_state_name_dash():
    parsed = parse_location("Idaho - Boise")
    assert parsed.city == "Boise"
    assert parsed.region == "Idaho"
    assert parsed.country_code == "US"


def test_parse_location_city_recovers_past_leading_facility_id():
    # Brand-word suffix ("Dialysis") is deliberately left in city — not
    # safely separable from a real multi-word city name without guessing.
    parsed = parse_location("05252 - Two Rivers Dialysis")
    assert parsed.city == "Two Rivers Dialysis"


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


def test_parse_location_resolves_city_past_direction_suffix_street_address():
    parsed = parse_location("3500 Marvin Rd NE, Lacey,WA 98516-1423")
    assert parsed.city == "Lacey"
    assert parsed.region == "WA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("7828 Georgia Ave NW, Washington,DC 20012-1305")
    assert parsed2.city == "Washington"
    assert parsed2.region == "DC"


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


def test_parse_location_region_set_even_when_second_token_is_non_city_phrase():
    parsed = parse_location("USA, ID, Home Office")
    assert parsed.city is None
    assert parsed.region == "ID"
    assert parsed.country_code == "US"

    parsed2 = parse_location("AZ, US")
    assert parsed2.city is None
    assert parsed2.region == "AZ"
    assert parsed2.country_code == "US"


def test_parse_location_resolves_dash_state_paren_zip_shape():
    parsed = parse_location("Laredo-Texas(78043)")
    assert parsed.city == "Laredo"
    assert parsed.region == "Texas"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Killeen-Texas(76548)")
    assert parsed2.city == "Killeen"
    assert parsed2.region == "Texas"
    assert parsed2.country_code == "US"
