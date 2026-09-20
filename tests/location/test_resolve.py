"""Tests for scraper/location/resolve.py's resolve_country_from_location.

The first test below (test_resolve_country_city_state_us) imports through
the scraper.location_resolver back-compat shim instead of the real module
directly, specifically to guard the shim itself against silent breakage —
every other test here imports the real implementation.
"""

from scraper.location.resolve import resolve_country_from_location
from scraper.location_resolver import (
    resolve_country_from_location as resolve_country_from_location_via_shim,
)


def test_resolve_country_city_state_us_via_shim():
    # Guards scraper.location_resolver's back-compat re-export itself.
    assert resolve_country_from_location_via_shim("San Francisco, CA") == "US"


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


def test_resolve_country_bare_city_name():
    # A location with no country/province/ISO signal at all — resolved via
    # BARE_CITY_NAME_TO_COUNTRY, the gazetteer-derived lowest-priority
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
    # These were valid single-country entries when BARE_CITY_NAME_TO_COUNTRY
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
    # affected by BARE_CITY_NAME_TO_COUNTRY's shrink at all.
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


def test_new_bare_cities():
    assert resolve_country_from_location("Cork") == "IE"
    assert resolve_country_from_location("Sherbrooke") == "CA"
    assert resolve_country_from_location("Denver") == "US"
    assert resolve_country_from_location("Tianjin") == "CN"
    assert resolve_country_from_location("Frankfurt am Main") == "DE"


def test_round_5_native_country_names_and_verified_cities():
    assert resolve_country_from_location("上海, 中国") == "CN"
    assert resolve_country_from_location("東根, 日本, 山形") == "JP"
    assert resolve_country_from_location("대한민국 서울") == "KR"
    assert resolve_country_from_location("Barcelona, España") == "ES"
    assert resolve_country_from_location("Genève, Suisse") == "CH"
    assert resolve_country_from_location("Zürich") == "CH"
    assert resolve_country_from_location("Zagreb") == "HR"
    assert resolve_country_from_location("Zaventem") == "BE"
    assert resolve_country_from_location("Warszawa") == "PL"
    assert resolve_country_from_location("Warsaw") == "PL"
    assert resolve_country_from_location("Krakow") == "PL"
    assert resolve_country_from_location("Reykjavik") == "IS"
    assert resolve_country_from_location("Vilnius") == "LT"
    assert resolve_country_from_location("Riga") == "LV"
    assert resolve_country_from_location("Tallinn") == "EE"
    assert resolve_country_from_location("Sofia") == "BG"
    assert resolve_country_from_location("Sarajevo") == "BA"
    assert resolve_country_from_location("Salzburg") == "AT"
    assert resolve_country_from_location("Innsbruck") == "AT"
    assert resolve_country_from_location("Graz") == "AT"
    assert resolve_country_from_location("Bologna") == "IT"
    assert resolve_country_from_location("Bilbao") == "ES"
    assert resolve_country_from_location("Malmö") == "SE"
    assert resolve_country_from_location("Tampere") == "FI"
    assert resolve_country_from_location("Trondheim") == "NO"
    assert resolve_country_from_location("Stavanger") == "NO"
    assert resolve_country_from_location("Odense") == "DK"
    assert resolve_country_from_location("Aalborg") == "DK"


def test_round_8_improvements():
    # 1. District of Columbia in US_STATE_TOKENS
    assert resolve_country_from_location("Washington Navy Yard, District of Columbia") == "US"
    assert resolve_country_from_location("Joint Base Anacostia-Bolling, District of Columbia") == "US"
    assert resolve_country_from_location("District of Columbia") == "US"

    # 2. Former / variant country name aliases
    assert resolve_country_from_location("Macedonia") == "MK"
    assert resolve_country_from_location("FYROM") == "MK"
    assert resolve_country_from_location("Macedonia, The Former Yugoslav Republic Of") == "MK"
    assert resolve_country_from_location("Swaziland") == "SZ"
    assert resolve_country_from_location("Burma") == "MM"
    assert resolve_country_from_location("U.S. Virgin Islands") == "VI"
    assert resolve_country_from_location("US Virgin Islands") == "VI"

    # 3. New sub-national regions — Malaysia
    assert resolve_country_from_location("Kuala Lumpur, Selangor") == "MY"
    assert resolve_country_from_location("Johor Bahru, Johor") == "MY"
    assert resolve_country_from_location("George Town, Penang") == "MY"
    assert resolve_country_from_location("Ipoh, Perak") == "MY"
    assert resolve_country_from_location("Sabah") == "MY"
    assert resolve_country_from_location("Sarawak") == "MY"
    assert resolve_country_from_location("Malacca") == "MY"

    # 4. New sub-national regions — Indonesia
    assert resolve_country_from_location("Surabaya, East Java") == "ID"
    assert resolve_country_from_location("Bandung, West Java") == "ID"
    assert resolve_country_from_location("Semarang, Central Java") == "ID"
    assert resolve_country_from_location("Medan, North Sumatra") == "ID"
    assert resolve_country_from_location("Yogyakarta") == "ID"

    # 5. New sub-national regions — UK additional counties
    assert resolve_country_from_location("Stevenage, Hertfordshire") == "GB"
    assert resolve_country_from_location("Crawley, West Sussex") == "GB"
    assert resolve_country_from_location("Sheffield, South Yorkshire") == "GB"
    assert resolve_country_from_location("Leeds, West Yorkshire") == "GB"
    assert resolve_country_from_location("Shrewsbury, Shropshire") == "GB"
    assert resolve_country_from_location("Carlisle, Cumbria") == "GB"
    assert resolve_country_from_location("Dorchester, Dorset") == "GB"
    assert resolve_country_from_location("East Riding of Yorkshire") == "GB"

    # 6. New sub-national regions — Australia Northern Territory
    assert resolve_country_from_location("Darwin, Northern Territory") == "AU"
    assert resolve_country_from_location("Northern Territory") == "AU"

    # 7. New bare cities — Philippines
    assert resolve_country_from_location("Davao") == "PH"
    assert resolve_country_from_location("Cagayan de Oro") == "PH"
    assert resolve_country_from_location("Cebu City") == "PH"
    assert resolve_country_from_location("Iloilo") == "PH"
    assert resolve_country_from_location("Muntinlupa") == "PH"
    assert resolve_country_from_location("Pasay") == "PH"

    # 8. New bare cities — Malaysia
    assert resolve_country_from_location("Gelang Patah") == "MY"
    assert resolve_country_from_location("Kuching") == "MY"
    assert resolve_country_from_location("Shah Alam") == "MY"
    assert resolve_country_from_location("Sibu") == "MY"

    # 9. New bare cities — Turkey
    assert resolve_country_from_location("Gebze") == "TR"
    assert resolve_country_from_location("Maslak") == "TR"

    # 10. New bare cities — UK
    assert resolve_country_from_location("Middlesbrough") == "GB"
    assert resolve_country_from_location("Harlow") == "GB"
    assert resolve_country_from_location("Glenrothes") == "GB"
    assert resolve_country_from_location("Wolverhampton") == "GB"

    # 11. New bare cities — Switzerland
    assert resolve_country_from_location("Meyrin") == "CH"
    assert resolve_country_from_location("Schwyz") == "CH"

    # 12. New bare cities — VI
    assert resolve_country_from_location("Charlotte Amalie") == "VI"
    assert resolve_country_from_location("Saint Croix") == "VI"

    # 13. New bare cities — Mexico
    assert resolve_country_from_location("Tijuana") == "MX"
    assert resolve_country_from_location("Hermosillo") == "MX"

    # 14. New bare cities — Africa capitals (sampling)
    assert resolve_country_from_location("Accra") == "GH"
    assert resolve_country_from_location("Abuja") == "NG"
    assert resolve_country_from_location("Addis Ababa") == "ET"
    assert resolve_country_from_location("Kampala") == "UG"
    assert resolve_country_from_location("Kinshasa") == "CD"
    assert resolve_country_from_location("Ouagadougou") == "BF"
    assert resolve_country_from_location("Windhoek") == "NA"
    assert resolve_country_from_location("Kigali") == "RW"

    # 15. New bare cities — Middle East
    assert resolve_country_from_location("Muscat") == "OM"
    assert resolve_country_from_location("Manama") == "BH"
    assert resolve_country_from_location("Kuwait City") == "KW"
    assert resolve_country_from_location("Beirut") == "LB"
    assert resolve_country_from_location("Sanaa") == "YE"

    # 16. New bare cities — SEA
    assert resolve_country_from_location("Yangon") == "MM"
    assert resolve_country_from_location("Mandalay") == "MM"
    assert resolve_country_from_location("Vientiane") == "LA"
    assert resolve_country_from_location("Nay Pyi Taw") == "MM"
    assert resolve_country_from_location("Bandar Seri Begawan") == "BN"
    assert resolve_country_from_location("Dili") == "TL"

    # 17. New bare cities — Caucasus / Central Asia
    assert resolve_country_from_location("Tbilisi") == "GE"
    assert resolve_country_from_location("Yerevan") == "AM"
    assert resolve_country_from_location("Baku") == "AZ"
    assert resolve_country_from_location("Tashkent") == "UZ"
    assert resolve_country_from_location("Minsk") == "BY"
    assert resolve_country_from_location("Chisinau") == "MD"

    # 18. New bare cities — Balkans / EU small
    assert resolve_country_from_location("Tirana") == "AL"
    assert resolve_country_from_location("Pristina") == "XK"
    assert resolve_country_from_location("Podgorica") == "ME"
    assert resolve_country_from_location("Vaduz") == "LI"
    assert resolve_country_from_location("Andorra la Vella") == "AD"

    # 19. DNU- prefix stripping
    assert resolve_country_from_location("DNU-IDN-JW-JAKARTA") == "ID"
    assert resolve_country_from_location("DNU-MEX-NLE-MONTERREY") == "MX"
    assert resolve_country_from_location("DNU-BRA-SP-SAO-PAULO") == "BR"
    assert resolve_country_from_location("DNU-ID-JW-JAKARTA") == "ID"
    assert resolve_country_from_location("DNU-MX-NLE-MONTERREY") == "MX"

    # 20. Trailing store/RDC suffix stripping — strips the numeric ID suffix
    # so downstream city/state extraction can proceed normally.
    # CHARLOTTE is in BARE_CITY_NAME_TO_COUNTRY -> US
    assert resolve_country_from_location("CHARLOTTE FDC/BDC - 5955") == "US"
    # WESTFIELD alone doesn't resolve, but with state token it does
    assert resolve_country_from_location("QUINCY, MA STORE - 1915") == "US"

    # 21. Trailing token bare city lookup
    assert resolve_country_from_location("Pudong, Shanghai") == "CN"
    assert resolve_country_from_location("Lancaster Luminaire Building, Hanoi") == "VN"
    assert resolve_country_from_location("Some Office, Davao") == "PH"

    # 22. First-token city + numeric address
    assert resolve_country_from_location("Shanghai, 100 Nanjing Road") == "CN"
    assert resolve_country_from_location("Tokyo, 1-1 Marunouchi") == "JP"
    assert resolve_country_from_location("Chicago, 233 S Wacker Dr") == "US"
    assert resolve_country_from_location("Seoul, 100 Gangnam-daero") == "KR"

    # 23. Safety checks — no new regressions
    assert resolve_country_from_location("Mumbai Office") is None
    assert resolve_country_from_location("CPO - Copenhagen Office") is None


def test_leading_iso3_comma_shape():
    # LEADING_ISO3_RE matches a comma delimiter as well as a dash — a
    # widening beyond the original dash-only pattern, for vendor feeds that
    # use "<ISO3>, <City>" instead of "<ISO3> - <City>".
    assert resolve_country_from_location("BRA, Sao Paulo") == "BR"
    assert resolve_country_from_location("bra, sao paulo") == "BR"


def test_bare_alpha3_whole_string():
    # A bare alpha-3 code as the entire (stripped) string, with no other
    # token at all — falls back to alpha3_to_alpha2 on the whole normalized
    # string, distinct from the trailing "<City>, <ISO3>" tier above.
    assert resolve_country_from_location("BRA") == "BR"
    assert resolve_country_from_location("bra") == "BR"
