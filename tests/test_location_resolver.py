from scraper.location_resolver import parse_location, resolve_country_from_location


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
    assert resolve_country_from_location("Montreal") == "CA"
    assert resolve_country_from_location("Toronto") == "CA"
    assert resolve_country_from_location("Mumbai") == "IN"
    assert resolve_country_from_location("Shanghai") == "CN"
    # Case-insensitive, matching the function's overall lowercasing.
    assert resolve_country_from_location("MONTREAL") == "CA"


def test_resolve_country_bare_city_name_excludes_known_false_positives():
    # "apac"/"federal" each have exactly one gazetteer match (a real but
    # obscure town) but were deliberately excluded as unsafe to trust bare —
    # confirms they were left out on purpose, not missed.
    assert resolve_country_from_location("APAC") is None
    assert resolve_country_from_location("Federal") is None


def test_resolve_country_bare_city_name_is_whole_string_only():
    # Must not fire on a city name embedded in a longer string — that's a
    # different signal (or lack thereof), not the bare-name fallback's job.
    assert resolve_country_from_location("Montreal Office") is None
    # Already resolves via the name-matching tier before ever reaching the
    # bare-city fallback.
    assert resolve_country_from_location("Montreal, Canada") == "CA"


def test_resolve_country_bare_city_name_second_expansion():
    # Re-derived against prod's actual unresolved-location strings (2026-09)
    # — same single-country-match method as the original table, just a
    # second pass against fresh data.
    assert resolve_country_from_location("Chicago") == "US"
    assert resolve_country_from_location("Berlin") == "DE"
    assert resolve_country_from_location("Prague") == "CZ"
    assert resolve_country_from_location("Kyiv") == "UA"
    assert resolve_country_from_location("South San Francisco") == "US"


def test_resolve_country_bare_city_name_excludes_genuine_ambiguity():
    # These have more than one country match in the gazetteer (confirmed via
    # the same derivation script) — must stay None rather than guess, even
    # though they're common, well-known city names.
    assert resolve_country_from_location("San Francisco") is None  # US/AR/PH/CR/SV
    assert resolve_country_from_location("Ottawa") is None  # CA/US
    assert resolve_country_from_location("Hyderabad") is None  # IN/PK
    assert resolve_country_from_location("London") is None  # CA/GB
