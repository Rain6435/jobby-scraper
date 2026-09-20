"""Tests for scraper/location/parse.py's parse_location and ParsedLocation.

The first test below (test_parse_location_country_code_populated_via_shim)
imports through the scraper.location_resolver back-compat shim instead of
the real module directly, specifically to guard the shim itself against
silent breakage — every other test here imports the real implementation.
"""

from scraper.location.parse import parse_location
from scraper.location.resolve import resolve_country_from_location
from scraper.location_resolver import parse_location as parse_location_via_shim


def test_parse_location_country_code_populated_via_shim():
    # Guards scraper.location_resolver's back-compat re-export itself.
    parsed = parse_location_via_shim("San Francisco, CA")
    assert parsed.country_code == "US"


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


# --- City names that collide with a country name ("Lebanon, TN", "Jordan, --
# --- MN", "Mexico, ME") — extends the existing US-state/CA-province ---
# --- name-collision guard to ISO_NAME_TO_CODE/LOCATION_ALIASES ---


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
    # itself is in CITY_REGION_COLLISION_TO_COUNTRY (no real US town
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
    # No city at all — CITY_REGION_COLLISION_TO_COUNTRY has nothing to
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


# --- CITY_REGION_COLLISION_TO_COUNTRY — data-derived (city, collision- --
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


# --- Accented city spelling ("München, DE") missing the --
# --- CITY_REGION_COLLISION_TO_COUNTRY correction that its ASCII- --
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
    # separate table (ALPHA3_US_CA_TOKENS) had to recognize these too.
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


# --- CA-province collision codes ("pe" Prince Edward Island/Peru, "nl" --
# --- Newfoundland and Labrador/Netherlands, "sk" Saskatchewan/ --
# --- Slovakia) — CITY_REGION_COLLISION_TO_COUNTRY's original derivation --
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
# --- correctly via ISO_NAME_TO_CODE, but nothing extracted tokens[1] --
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


def test_parse_location_resolves_dash_state_paren_zip_shape():
    parsed = parse_location("Laredo-Texas(78043)")
    assert parsed.city == "Laredo"
    assert parsed.region == "Texas"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Killeen-Texas(76548)")
    assert parsed2.city == "Killeen"
    assert parsed2.region == "Texas"
    assert parsed2.country_code == "US"


# --- State-dash-city-dash-facility ("IL-Channahon-Replenishment Center") ---


def test_state_dash_city_dash_facility():
    parsed = parse_location("IL-Channahon-Replenishment Center")
    assert parsed.city == "Channahon"
    assert parsed.region == "IL"
    assert parsed.country_code == "US"

    parsed2 = parse_location("SC-Aiken- PAM Hlth Rehab Hosp of Aiken")
    assert parsed2.city == "Aiken"
    assert parsed2.region == "SC"
    assert parsed2.country_code == "US"

    parsed3 = parse_location("NC-Rocky Mount-PAM Specialty Hospital")
    assert parsed3.city == "Rocky Mount"
    assert parsed3.region == "NC"
    assert parsed3.country_code == "US"


# --- Trailing parenthetical (City, Region/Country) ---


def test_trailing_paren_city_region():
    parsed = parse_location("HOKA Newbury Street Retail Store (Boston, MA)")
    assert parsed.city == "Boston"
    assert parsed.region == "MA"
    assert parsed.country_code == "US"

    parsed2 = parse_location("UGG Leesburg  Premium Outlets (Leesburg, VA)")
    assert parsed2.city == "Leesburg"
    assert parsed2.region == "VA"
    assert parsed2.country_code == "US"

    parsed3 = parse_location("HOKA Toronto Eaton Centre (Toronto, ON)")
    assert parsed3.city == "Toronto"
    assert parsed3.region == "ON"
    assert parsed3.country_code == "CA"

    parsed4 = parse_location("HOKA Garibaldi Store (Milan, IT)")
    assert parsed4.city == "Milan"
    assert parsed4.country_code == "IT"


# --- Colon-delimited street address / store ID before city ---


def test_colon_address_city_and_store_id():
    parsed = parse_location("885 GEORGIA ST W:VANCOUVER")
    assert parsed.city == "VANCOUVER"

    parsed2 = parse_location("ST0189: Victoriaville")
    assert parsed2.city == "Victoriaville"

    parsed3 = parse_location("407 8 AVE SW:CALGARY")
    assert parsed3.city == "CALGARY"

    parsed4 = parse_location("ROYAL BANK PLAZA, 200 BAY ST:TORONTO")
    assert parsed4.city == "TORONTO"


# --- Leading & bare ISO alpha-3 country codes ---


def test_alpha3_leading_and_bare():
    parsed = parse_location("IND, GURGAON")
    assert parsed.city == "GURGAON"
    assert parsed.country_code == "IN"

    parsed_bare = parse_location("CZE")
    assert parsed_bare.city is None
    assert parsed_bare.country_code == "CZ"

    parsed_bra = parse_location("BRA")
    assert parsed_bra.city is None
    assert parsed_bra.country_code == "BR"

    parsed_us = parse_location("USA, GA, Remote")
    assert parsed_us.region == "GA"
    assert parsed_us.country_code == "US"
    assert parsed_us.is_remote is True


# --- Missing country aliases (Turkey, Deutschland, Korea, Republic of) ---


def test_new_country_aliases():
    parsed_turkey = parse_location("Turkey Remote Office")
    assert parsed_turkey.country_code == "TR"
    assert parsed_turkey.is_remote is True

    parsed_ist = parse_location("Istanbul, Turkey")
    assert parsed_ist.city == "Istanbul"
    assert parsed_ist.country_code == "TR"

    parsed_de = parse_location("Biberach, Deutschland, Baden-Württemberg")
    assert parsed_de.city == "Biberach"
    assert parsed_de.country_code == "DE"

    parsed_kr = parse_location("Korea, Republic of - Seoul")
    assert parsed_kr.country_code == "KR"


# --- Trailing attendance / hybrid policy suffix ---


def test_trailing_attendance_policy():
    parsed = parse_location("Seattle 2+ days in office")
    assert parsed.city == "Seattle"
    assert parsed.country_code == "US"

    parsed2 = parse_location("Herndon 2+ days in office")
    assert parsed2.city == "Herndon"
    assert parsed2.country_code is None


# --- Full state/province name in trailing dash suffix ---


def test_trailing_state_dash_suffix_full_name():
    parsed = parse_location("USA, Virginia - Full Time Remote")
    assert parsed.city is None
    assert parsed.region == "Virginia"
    assert parsed.country_code == "US"
    assert parsed.is_remote is True

    parsed2 = parse_location("CAN, British Columbia - Full Time Remote")
    assert parsed2.city is None
    assert parsed2.region == "British Columbia"
    assert parsed2.country_code == "CA"
    assert parsed2.is_remote is True


# --- Leading ISO2 country code + dash ("AE-Abu Dhabi-Mussafah Garden", "FR-Paris") ---


def test_leading_iso2_dash_and_facility():
    parsed = parse_location("AE-Abu Dhabi-Mussafah Garden")
    assert parsed.city == "Abu Dhabi"
    assert parsed.country_code == "AE"

    parsed2 = parse_location("FR-Paris")
    assert parsed2.city == "Paris"
    assert parsed2.country_code == "FR"

    parsed3 = parse_location("SE-Stockholm-MSO")
    assert parsed3.city == "Stockholm"
    assert parsed3.country_code == "SE"


# --- Space-joined "CAN <Province> <City>" ---


def test_can_space_prov_city():
    parsed = parse_location("CAN Alberta Edmonton")
    assert parsed.city == "Edmonton"
    assert parsed.region == "Alberta"
    assert parsed.country_code == "CA"

    parsed2 = parse_location("CAN Quebec Québec")
    assert parsed2.city == "Québec"
    assert parsed2.region == "Quebec"
    assert parsed2.country_code == "CA"


# --- "<City> - <ISO2>" ---


def test_city_dash_iso2():
    parsed = parse_location("Guangzhou - CN")
    assert parsed.city == "Guangzhou"
    assert parsed.country_code == "CN"

    parsed2 = parse_location("Dublin - IE")
    assert parsed2.city == "Dublin"
    assert parsed2.country_code == "IE"


# --- "<City> - <State>" ---


def test_city_dash_state():
    parsed_city = parse_location("Jacksonville - Florida")
    assert parsed_city.city == "Jacksonville"
    assert parsed_city.region == "Florida"
    assert parsed_city.country_code == "US"

    parsed_city2 = parse_location("Salem - Ohio")
    assert parsed_city2.city == "Salem"
    assert parsed_city2.region == "Ohio"
    assert parsed_city2.country_code == "US"


# --- 2-token "<CountryAlias>, <City>" ---


def test_alias_city_two_tokens():
    parsed_uk = parse_location("UK, Bristol")
    assert parsed_uk.city == "Bristol"
    assert parsed_uk.country_code == "GB"

    parsed_uae = parse_location("UAE, Dubai")
    assert parsed_uae.city == "Dubai"
    assert parsed_uae.country_code == "AE"

    parsed_us = parse_location("USA, Atlanta")
    assert parsed_us.city == "Atlanta"
    assert parsed_us.country_code == "US"


# --- Round 3 Improvements ---


def test_french_street_address_and_colon_prefix():
    p1 = parse_location("135-1, rue Principale, Sainte-Justine")
    assert p1.city == "Sainte-Justine"

    p2 = parse_location("839 RTE JEAN GAUVIN:QUÉBEC")
    assert p2.city == "QUÉBEC"
    assert p2.country_code == "CA"


def test_circle_k_store_prefix_and_negative_lookahead():
    p1 = parse_location("27241 CIRCLE K GÄLLIVARE")
    assert p1.city == "GÄLLIVARE"

    p2 = parse_location("10257 Circle K Maribo")
    assert p2.city == "Maribo"
    assert p2.country_code == "DK"

    # Ensure ordinary circle street name still works
    p3 = parse_location("500 Logan Circle, Washington, DC")
    assert p3.city == "Washington"
    assert p3.region == "DC"
    assert p3.country_code == "US"


def test_city_st_facility():
    p1 = parse_location("Bloomington MN - Country Inn Bloomington")
    assert p1.city == "Bloomington"
    assert p1.region == "MN"
    assert p1.country_code == "US"

    p2 = parse_location("Denver PA - 465 Swamp Bridge Road")
    assert p2.city == "Denver"
    assert p2.region == "PA"
    assert p2.country_code == "US"

    p3 = parse_location("Hagerstown MD-Op Ctr")
    assert p3.city == "Hagerstown"
    assert p3.region == "MD"
    assert p3.country_code == "US"


def test_trailing_address_strip():
    p1 = parse_location("Saskatoon-1816 McOrmond Dr")
    assert p1.city == "Saskatoon"
    assert p1.country_code == "CA"

    p2 = parse_location("Austin-5900 E Ben White Blvd (10703)")
    assert p2.city == "Austin"
    assert p2.country_code == "US"

    p3 = parse_location("Edmonton - 103 St")
    assert p3.city == "Edmonton"


def test_city_dash_alpha3_code():
    p1 = parse_location("Manchester - GBR")
    assert p1.city == "Manchester"
    assert p1.country_code == "GB"

    assert resolve_country_from_location("Manchester - GBR") == "GB"


def test_iso3_region_city_and_iso3_city():
    p1 = parse_location("CAN-ON-Kitchener")
    assert p1.city == "Kitchener"
    assert p1.region == "ON"
    assert p1.country_code == "CA"

    p2 = parse_location("CAN-AB-Calgary-112 4th Avenue SW")
    assert p2.city == "Calgary"
    assert p2.region == "AB"
    assert p2.country_code == "CA"

    p3 = parse_location("USA-AK-Home Office")
    assert p3.region == "AK"
    assert p3.country_code == "US"

    p4 = parse_location("BRA-Barueri")
    assert p4.city == "Barueri"
    assert p4.country_code == "BR"


def test_new_country_aliases_round_2():
    # Renamed from a duplicate `test_new_country_aliases` (same name as the
    # earlier test above) found while splitting this file — pytest was
    # silently shadowing this one under the original combined file, so it
    # never actually ran. Un-shadowed here rather than left duplicated.
    assert resolve_country_from_location("Istanbul, Türkiye") == "TR"
    assert resolve_country_from_location("Ho Chi Minh, Viet Nam") == "VN"
    assert resolve_country_from_location("São Paulo, Brasil") == "BR"
    assert resolve_country_from_location("Remote, KSA") == "SA"

    p_prc = parse_location("PRC, Shanghai")
    assert p_prc.city == "Shanghai"
    assert p_prc.country_code == "CN"


def test_non_city_phrase_first():
    p1 = parse_location("Remote, Los Angeles")
    assert p1.city == "Los Angeles"
    assert p1.is_remote is True

    p2 = parse_location("Virtual, Seattle")
    assert p2.city == "Seattle"
    assert p2.is_remote is True


def test_non_city_phrase_first_covers_full_non_city_phrases_set():
    # NON_CITY_PHRASES also includes "work from home"/"wfh"/"home office" —
    # not just "remote"/"virtual" — as a leading, non-city first token.
    p1 = parse_location("Work From Home, Austin")
    assert p1.city == "Austin"
    assert p1.is_remote is True

    p2 = parse_location("WFH, Denver")
    assert p2.city == "Denver"
    assert p2.is_remote is True

    p3 = parse_location("Home Office, Chicago")
    assert p3.city == "Chicago"


# --- Round 4 tests: Country-State-City, City-states, Sysco/office prefixes, ---
# --- French double-space addresses, and Russian Federation alias ---


def test_country_state_city_dash_patterns():
    p1 = parse_location("US - Florida - Pensacola")
    assert p1.city == "Pensacola"
    assert p1.region == "Florida"
    assert p1.country_code == "US"

    p2 = parse_location("USA - Florida - Miami")
    assert p2.city == "Miami"
    assert p2.region == "Florida"
    assert p2.country_code == "US"

    p3 = parse_location("US-CA - San Diego")
    assert p3.city == "San Diego"
    assert p3.region == "CA"
    assert p3.country_code == "US"

    p4 = parse_location("CA - British Columbia - Vancouver")
    assert p4.city == "Vancouver"
    assert p4.region == "British Columbia"
    assert p4.country_code == "CA"

    p5 = parse_location("CAN - Ontario - Ottawa")
    assert p5.city == "Ottawa"
    assert p5.region == "Ontario"
    assert p5.country_code == "CA"

    p6 = parse_location("US-CA - El Segundo")
    assert p6.city == "El Segundo"
    assert p6.region == "CA"
    assert p6.country_code == "US"

    p7 = parse_location("CA - Alberta - Calgary")
    assert p7.city == "Calgary"
    assert p7.region == "Alberta"
    assert p7.country_code == "CA"

    p8 = parse_location("USA - WI - Marinette - 1931 Marinette Avenue")
    assert p8.city == "Marinette"
    assert p8.region == "WI"
    assert p8.country_code == "US"

    p9 = parse_location("US-Ohio-Tallmadge-184 South Avenue")
    assert p9.city == "Tallmadge"
    assert p9.region == "Ohio"
    assert p9.country_code == "US"

    p10 = parse_location("US - Richmond - VA")
    assert p10.city == "Richmond"
    assert p10.region == "VA"
    assert p10.country_code == "US"

    p11 = parse_location("US - Betts - SD")
    assert p11.city == "Betts"
    assert p11.region == "SD"
    assert p11.country_code == "US"


def test_international_iso3_region_city():
    p1 = parse_location("GBR - England - Reading")
    assert p1.city == "Reading"
    assert p1.country_code == "GB"

    p2 = parse_location("DEU - Hesse - Biebesheim")
    assert p2.city == "Biebesheim"
    assert p2.country_code == "DE"

    p3 = parse_location("IND - Maharashtra - Mumbai")
    assert p3.city == "Mumbai"
    assert p3.country_code == "IN"

    p4 = parse_location("CHN - Sichuan - Chengdu")
    assert p4.city == "Chengdu"
    assert p4.country_code == "CN"

    p5 = parse_location("MEX - Jalisco - Guadalajara")
    assert p5.city == "Guadalajara"
    assert p5.country_code == "MX"


def test_duplicate_tokens_new_york_and_city_states():
    p_ny = parse_location("New York, New York")
    assert p_ny.city is None
    assert p_ny.region == "New York"
    assert p_ny.country_code == "US"

    p_ny_us = parse_location("New York, New York, US")
    assert p_ny_us.city == "New York"
    assert p_ny_us.region == "New York"
    assert p_ny_us.country_code == "US"

    p_sg = parse_location("Singapore, Singapore")
    assert p_sg.city == "Singapore"
    assert p_sg.country_code == "SG"

    p_sg_sg = parse_location("Singapore, Singapore, SG")
    assert p_sg_sg.city == "Singapore"
    assert p_sg_sg.country_code == "SG"

    p_mc = parse_location("Monaco, Monaco")
    assert p_mc.city == "Monaco"
    assert p_mc.country_code == "MC"

    p_lu = parse_location("Luxembourg, Luxembourg")
    assert p_lu.city == "Luxembourg"
    assert p_lu.country_code == "LU"

    p_dj = parse_location("Djibouti, Djibouti")
    assert p_dj.city == "Djibouti"
    assert p_dj.country_code == "DJ"

    p_sm = parse_location("San Marino, San Marino")
    assert p_sm.city == "San Marino"
    assert p_sm.country_code == "SM"

    p_kw = parse_location("Kuwait, Kuwait")
    assert p_kw.city == "Kuwait"
    assert p_kw.country_code == "KW"


def test_vendor_prefixes_and_store_suffixes():
    p_sysco1 = parse_location("Sysco Charlotte")
    assert p_sysco1.city == "Charlotte"
    assert p_sysco1.country_code == "US"

    p_sysco2 = parse_location("Sysco Idaho - Boise")
    assert p_sysco2.city == "Boise"
    assert p_sysco2.region == "Idaho"
    assert p_sysco2.country_code == "US"

    p_off1 = parse_location("SERVICES OFFICE, LAKELAND - 1435")
    assert p_off1.city == "LAKELAND"

    p_off2 = parse_location("ASKUITY OFFICE, TORONTO - 2595")
    assert p_off2.city == "TORONTO"

    p_rdc = parse_location("WESTFIELD RDC - 5221")
    assert p_rdc.city == "WESTFIELD"

    p_fdc = parse_location("CHARLOTTE FDC/BDC - 5955")
    assert p_fdc.city == "CHARLOTTE"

    p_fr1 = parse_location("159, boulevard Bégin  Sainte-Claire")
    assert p_fr1.city == "Sainte-Claire"

    p_fr2 = parse_location("212 A, boulevard Labelle  Rosemère")
    assert p_fr2.city == "Rosemère"


def test_round_4_bare_cities_and_aliases():
    p_ru = parse_location("Saint Petersburg, Russian Federation")
    assert p_ru.city == "Saint Petersburg"
    assert p_ru.country_code == "RU"
    assert resolve_country_from_location("Saint Petersburg, Russian Federation") == "RU"

    assert resolve_country_from_location("Wuhan") == "CN"
    assert resolve_country_from_location("Lahore") == "PK"
    assert resolve_country_from_location("Thunder Bay") == "CA"
    assert resolve_country_from_location("Fort Worth") == "US"
    assert resolve_country_from_location("St. Catharines") == "CA"


def test_round_5_sub_national_regions():
    p_mx = parse_location("Guadalajara, Jalisco")
    assert p_mx.city == "Guadalajara"
    assert p_mx.region is None
    assert p_mx.country_code == "MX"
    assert resolve_country_from_location("Guadalajara, Jalisco") == "MX"

    p_cn = parse_location("Hangzhou, Zhejiang")
    assert p_cn.city == "Hangzhou"
    assert p_cn.region is None
    assert p_cn.country_code == "CN"
    assert resolve_country_from_location("Hangzhou, Zhejiang") == "CN"

    p_br = parse_location("Pindamonhangaba, São Paulo")
    assert p_br.city == "Pindamonhangaba"
    assert p_br.region is None
    assert p_br.country_code == "BR"
    assert resolve_country_from_location("Pindamonhangaba, São Paulo") == "BR"

    p_de = parse_location("Munich, Bavaria")
    assert p_de.city == "Munich"
    assert p_de.region is None
    assert p_de.country_code == "DE"
    assert resolve_country_from_location("Munich, Bavaria") == "DE"

    p_gb = parse_location("High Wycombe, Buckinghamshire")
    assert p_gb.city == "High Wycombe"
    assert p_gb.region is None
    assert p_gb.country_code == "GB"
    assert resolve_country_from_location("High Wycombe, Buckinghamshire") == "GB"

    p_au1 = parse_location("Cohuna, VIC")
    assert p_au1.city == "Cohuna"
    assert p_au1.region is None
    assert p_au1.country_code == "AU"
    assert resolve_country_from_location("Cohuna, VIC") == "AU"

    p_au2 = parse_location("Brisbane, Queensland")
    assert p_au2.city == "Brisbane"
    assert p_au2.region is None
    assert p_au2.country_code == "AU"
    assert resolve_country_from_location("Brisbane, Queensland") == "AU"


def test_round_5_noise_and_address_patterns():
    # Store home office pattern
    p_ho = parse_location("6361 Ossining NY Home Office")
    assert p_ho.city == "Ossining"
    assert p_ho.region == "NY"
    assert p_ho.country_code == "US"
    assert resolve_country_from_location("6361 Ossining NY Home Office") == "US"

    # Office suffixes
    p_off = parse_location("Troy, MI Group Sales Office (035)")
    assert p_off.city == "Troy"
    assert p_off.region == "MI"
    assert p_off.country_code == "US"
    assert resolve_country_from_location("Troy, MI Group Sales Office (035)") == "US"

    # Lowe's prefix and facility suffix without dash
    p_lowes = parse_location("Lowe's New Caney, TX BDC 3465")
    assert p_lowes.city == "New Caney"
    assert p_lowes.region == "TX"
    assert p_lowes.country_code == "US"
    assert resolve_country_from_location("Lowe's New Caney, TX BDC 3465") == "US"

    # Remote work prefixes and More... suffixes
    p_nv = parse_location("Work at Home - Nevada")
    assert p_nv.region == "Nevada"
    assert p_nv.country_code == "US"
    assert resolve_country_from_location("Work at Home - Nevada") == "US"

    p_on = parse_location("Work From Home - Ontario")
    assert p_on.region == "Ontario"
    assert p_on.country_code == "CA"
    assert resolve_country_from_location("Work From Home - Ontario") == "CA"

    p_mi = parse_location("Michigan Remote Work, More...")
    assert p_mi.region == "Michigan"
    assert p_mi.country_code == "US"
    assert resolve_country_from_location("Michigan Remote Work, More...") == "US"

    # Single-token states
    p_nev = parse_location("Nevada")
    assert p_nev.region == "Nevada"
    assert p_nev.country_code == "US"
    assert resolve_country_from_location("Nevada") == "US"

    # International postal codes
    p_br_zip = parse_location("Sao Paulo, São Paulo, BRA, 04578-133")
    assert p_br_zip.country_code == "BR"
    assert resolve_country_from_location("Sao Paulo, São Paulo, BRA, 04578-133") == "BR"

    p_at_zip = parse_location("Klagenfurt, Carinthia, AUT, 9020")
    assert p_at_zip.country_code == "AT"
    assert resolve_country_from_location("Klagenfurt, Carinthia, AUT, 9020") == "AT"

    p_uk_post = parse_location("5 Southampton Street, London WC2E 7HA")
    assert p_uk_post.city == "London"
    assert p_uk_post.country_code == "GB"
    assert resolve_country_from_location("5 Southampton Street, London WC2E 7HA") == "GB"

    # Trailing address dash with suite commas
    p_hou = parse_location("Houston - 1311 W. Sam Houston Pkwy N., Ste. 150 (10400)")
    assert p_hou.city == "Houston"
    assert p_hou.country_code is None


def test_round_6_improvements():
    # Four Seasons prefix
    p_fs_cn = parse_location("Four Seasons Dalian")
    assert p_fs_cn.city == "Dalian"
    assert p_fs_cn.country_code == "CN"
    assert resolve_country_from_location("Four Seasons Dalian") == "CN"

    p_fs_gb = parse_location("Four Seasons Hampshire")
    assert p_fs_gb.city == "Hampshire"
    assert p_fs_gb.country_code == "GB"
    assert resolve_country_from_location("Four Seasons Hampshire") == "GB"

    p_fs_us = parse_location("Four Seasons Nashville")
    assert p_fs_us.city == "Nashville"
    assert p_fs_us.country_code == "US"
    assert resolve_country_from_location("Four Seasons Nashville") == "US"

    # Freshpoint prefix
    p_fp = parse_location("Freshpoint Nashville")
    assert p_fp.city == "Nashville"
    assert p_fp.country_code == "US"
    assert resolve_country_from_location("Freshpoint Nashville") == "US"

    # Remote/Home prefix
    p_rh1 = parse_location("Remote/Home Indiana")
    assert p_rh1.region == "Indiana"
    assert p_rh1.country_code == "US"
    assert p_rh1.is_remote is True
    assert resolve_country_from_location("Remote/Home Indiana") == "US"

    p_rh2 = parse_location("Remote/Home Oklahoma")
    assert p_rh2.region == "Oklahoma"
    assert p_rh2.country_code == "US"
    assert p_rh2.is_remote is True
    assert resolve_country_from_location("Remote/Home Oklahoma") == "US"

    # Ngr store suffix
    p_ngr1 = parse_location("Tampa 1286 Ngr")
    assert p_ngr1.city == "Tampa"
    assert p_ngr1.country_code == "US"
    assert resolve_country_from_location("Tampa 1286 Ngr") == "US"

    p_ngr2 = parse_location("Memphis 1988 Ngr")
    assert p_ngr2.city == "Memphis"
    assert p_ngr2.country_code == "US"
    assert resolve_country_from_location("Memphis 1988 Ngr") == "US"

    # Metro Area / Area suffix
    p_ma1 = parse_location("Austin Metro Area")
    assert p_ma1.city == "Austin"
    assert p_ma1.country_code == "US"
    assert resolve_country_from_location("Austin Metro Area") == "US"

    p_ma2 = parse_location("Santiago De Querétaro_Area")
    assert p_ma2.city == "Santiago De Querétaro"
    assert p_ma2.country_code == "MX"
    assert resolve_country_from_location("Santiago De Querétaro_Area") == "MX"

    # Hub suffix
    p_hub1 = parse_location("Toronto, ON Hub")
    assert p_hub1.city == "Toronto"
    assert p_hub1.region == "ON"
    assert p_hub1.country_code == "CA"
    assert resolve_country_from_location("Toronto, ON Hub") == "CA"

    p_hub2 = parse_location("Vancouver, BC Hub")
    assert p_hub2.city == "Vancouver"
    assert p_hub2.region == "BC"
    assert p_hub2.country_code == "CA"
    assert resolve_country_from_location("Vancouver, BC Hub") == "CA"

    # Trailing city address after comma
    p_addr1 = parse_location("Ajax, 59 Westney Rd S")
    assert p_addr1.city == "Ajax"
    assert p_addr1.country_code == "CA"
    assert resolve_country_from_location("Ajax, 59 Westney Rd S") == "CA"

    p_addr2 = parse_location("Mississauga, 2 Prologis Blvd")
    assert p_addr2.city == "Mississauga"
    assert p_addr2.country_code == "CA"
    assert resolve_country_from_location("Mississauga, 2 Prologis Blvd") == "CA"

    # Verified safe unique bare cities
    assert resolve_country_from_location("Uzhhorod") == "UA"
    assert resolve_country_from_location("Köln") == "DE"
    assert resolve_country_from_location("Dortmund") == "DE"
    assert resolve_country_from_location("Lévis") == "CA"
    assert resolve_country_from_location("Longueuil") == "CA"
    assert resolve_country_from_location("São Bernardo Do Campo") == "BR"
    assert resolve_country_from_location("São José dos Campos") == "BR"
    assert resolve_country_from_location("Canberra") == "AU"
    assert resolve_country_from_location("Bordeaux") == "FR"
    assert resolve_country_from_location("Lyon") == "FR"
    assert resolve_country_from_location("Baku") == "AZ"
    assert resolve_country_from_location("Istanbul") == "TR"
    assert resolve_country_from_location("Osaka") == "JP"
    assert resolve_country_from_location("Kyoto") == "JP"
    assert resolve_country_from_location("Seoul") == "KR"
    assert resolve_country_from_location("Kuala Lumpur") == "MY"
    assert resolve_country_from_location("Budapest") == "HU"
    assert resolve_country_from_location("Johannesburg") == "ZA"
    assert resolve_country_from_location("Tunis") == "TN"


def test_round_7_improvements():
    # 1. UNIQLO format
    assert resolve_country_from_location("UNIQLO MA Burlington Mall(UQUS)") == "US"
    p_u1 = parse_location("UNIQLO MA Burlington Mall(UQUS)")
    assert p_u1.city == "Burlington Mall"
    assert p_u1.region == "MA"
    assert p_u1.country_code == "US"

    assert resolve_country_from_location("UNIQLO WA Tacoma mall(UQUS)") == "US"
    p_u2 = parse_location("UNIQLO WA Tacoma mall(UQUS)")
    assert p_u2.city == "Tacoma mall"
    assert p_u2.region == "WA"
    assert p_u2.country_code == "US"

    # 2. Desjardins Canadian financial cooperative
    assert resolve_country_from_location("Caisse Desjardins du Centre de Lotbinière") == "CA"
    assert resolve_country_from_location("Complexe Desjardins Montréal") == "CA"
    assert (
        resolve_country_from_location("Caisse populaire Desjardins d'Hochelaga-Maisonneuve") == "CA"
    )

    # 3. Trailing city address with country preserved
    assert resolve_country_from_location("Croydon, 69 PARK LANE, United Kingdom") == "GB"
    p_croydon = parse_location("Croydon, 69 PARK LANE, United Kingdom")
    assert p_croydon.city == "Croydon"
    assert p_croydon.country_code == "GB"

    # 4. Venue prefix with city and state extraction
    p_td = parse_location("TD Centre - North - 77 King Street West, Toronto, Ontario")
    assert p_td.city == "Toronto"
    assert p_td.region == "Ontario"
    assert p_td.country_code == "CA"
    assert (
        resolve_country_from_location("TD Centre - North - 77 King Street West, Toronto, Ontario")
        == "CA"
    )

    p_qc = parse_location("Head Office, Quebec City, QC")
    assert p_qc.city == "Quebec City"
    assert p_qc.region == "QC"
    assert p_qc.country_code == "CA"

    p_sh = parse_location("Carrefour de l'Estrie, Sherbrooke, QC")
    assert p_sh.city == "Sherbrooke"
    assert p_sh.region == "QC"
    assert p_sh.country_code == "CA"

    p_pa = parse_location("42 East Baltimore Pike, Media, Pennsylvania")
    assert p_pa.city == "Media"
    assert p_pa.region == "Pennsylvania"
    assert p_pa.country_code == "US"

    # 5. European 3+2 postal code
    assert resolve_country_from_location("Stockholm, SWE, 104 51") == "SE"

    # 6. French street address prefix with space before comma
    assert resolve_country_from_location("276, rue Papineau , Papineauville") == "CA"
    p_pap = parse_location("276, rue Papineau , Papineauville")
    assert p_pap.city == "Papineauville"
    assert p_pap.country_code == "CA"

    # 7. Sub-national regions
    assert resolve_country_from_location("Taguig City, National Capital Region (Manila)") == "PH"
    assert resolve_country_from_location("Pune, Maharashtra") == "IN"
    assert resolve_country_from_location("Bengaluru, Karnataka") == "IN"
    assert resolve_country_from_location("Yokohama, Kanagawa") == "JP"
    assert resolve_country_from_location("Barcelona, Catalonia") == "ES"
    assert resolve_country_from_location("Milan, Lombardy") == "IT"
    assert resolve_country_from_location("Rennes, Bretagne") == "FR"

    # 8. Verified safe bare cities
    assert resolve_country_from_location("Saint-Jean-sur-Richelieu") == "CA"
    assert resolve_country_from_location("Saint-Hyacinthe") == "CA"
    assert resolve_country_from_location("Saint-Eustache") == "CA"
    assert resolve_country_from_location("Pointe-Claire") == "CA"
    assert resolve_country_from_location("Amman") == "JO"
    assert resolve_country_from_location("Chiang Mai") == "TH"
    assert resolve_country_from_location("Taguig") == "PH"
    assert resolve_country_from_location("Mandaluyong") == "PH"
    assert resolve_country_from_location("Haderslev") == "DK"
    assert resolve_country_from_location("Brive-la-Gaillarde") == "FR"


# --- default_country fallback (opt-in, only fills a truly unresolved
# --- country_code — never overrides a country the string itself resolved) ---


def test_parse_location_default_country_fills_unresolved_country_code():
    parsed = parse_location("00146 - Puyallup Dialysis", default_country="US")
    assert parsed.country_code == "US"


def test_parse_location_default_country_never_overrides_resolved_country():
    parsed = parse_location("Berlin, DE", default_country="FR")
    assert parsed.country_code == "DE"


def test_parse_location_default_country_absent_by_default():
    parsed = parse_location("00146 - Puyallup Dialysis")
    assert parsed.country_code is None


def test_parse_location_default_country_none_is_a_noop():
    parsed = parse_location("00146 - Puyallup Dialysis", default_country=None)
    assert parsed.country_code is None
