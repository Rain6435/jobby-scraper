from scraper.location.resolve import resolve_country_from_location
from scraper.location_resolver import (
    resolve_country_from_location as resolve_country_from_location_via_shim,
)


def test_resolve_country_city_state_us():
    assert resolve_country_from_location("San Francisco, CA") == "US"


def test_resolve_country_city_state_us_via_shim():
    # Guards the backward-compat shim (scraper/location_resolver.py) itself
    # against silent breakage — every other test in this file imports
    # resolve_country_from_location directly from scraper.location.resolve.
    assert resolve_country_from_location_via_shim("San Francisco, CA") == "US"


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


def test_resolve_country_trailing_ca_after_province_is_canada_not_california():
    assert resolve_country_from_location("London, ON, CA") == "CA"
    assert resolve_country_from_location("Lethbridge, AB, CA") == "CA"


def test_resolve_country_bare_trailing_ca_still_california():
    # No distinct CA-province token before it — must stay the ordinary,
    # overwhelmingly common California reading. The new tier only fires
    # for the specific "<province>, ca" last-two-tokens shape.
    assert resolve_country_from_location("San Francisco, CA") == "US"
    assert resolve_country_from_location("Capitola, CA, United States") == "US"


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


def test_resolve_country_prioritizes_explicit_country_name_over_leading_collision_code():
    # Without the fix, "DE - Berlin, Germany" resolved to "US" (Delaware)
    # — confirmed live before this fix, since resolve_country_from_
    # location on the RAW string already correctly returns "DE" here, but
    # the leading-dash cleanup was reordering it into a shape that broke
    # that correct reading.
    assert resolve_country_from_location("DE - Berlin, Germany") == "DE"
    assert resolve_country_from_location("IN - Mumbai, India") == "IN"
    assert resolve_country_from_location("CA - Toronto, Canada") == "CA"


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
