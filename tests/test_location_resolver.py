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
