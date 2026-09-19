"""Free-text job-location string -> structured fields (country, city, region,
remote flag) plus a casing/whitespace-insensitive dedup key.

Country resolution is a manual Python port of jobby/utils/pipeline/
countryResolver.ts's resolveCountryFromLocation() — same alias tables (copied
verbatim, not just the shape), same layered matching order, same "never
guess, return None" contract. Keep both in sync by hand if aliases change;
there is no shared source file across the Python/TypeScript boundary.

country_code/city/region resolution is best-effort and deliberately
conservative about merging identity: normalized_key only folds whitespace/
case (never merges genuinely different place names), while the country/city/
region fields are additional structured metadata layered on top for
filtering, not used to decide whether two `locations` rows are "the same
place" (see get_or_create_locations in db.py).
"""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass

# Mirrors jobby/shared/countryResolver.ts's COUNTRY_NAMES (alpha-2 -> display
# name). Reversed here into name (lowercased) -> alpha-2 for lookup, avoiding
# a new dependency (e.g. pycountry) for what both sides already needed.
COUNTRY_NAMES: dict[str, str] = {
    "AF": "Afghanistan",
    "AX": "Åland Islands",
    "AL": "Albania",
    "DZ": "Algeria",
    "AS": "American Samoa",
    "AD": "Andorra",
    "AO": "Angola",
    "AI": "Anguilla",
    "AG": "Antigua and Barbuda",
    "AR": "Argentina",
    "AM": "Armenia",
    "AW": "Aruba",
    "AU": "Australia",
    "AT": "Austria",
    "AZ": "Azerbaijan",
    "BS": "Bahamas",
    "BH": "Bahrain",
    "BD": "Bangladesh",
    "BB": "Barbados",
    "BY": "Belarus",
    "BE": "Belgium",
    "BZ": "Belize",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BT": "Bhutan",
    "BO": "Bolivia",
    "BQ": "Bonaire, Sint Eustatius and Saba",
    "BA": "Bosnia and Herzegovina",
    "BW": "Botswana",
    "BR": "Brazil",
    "IO": "British Indian Ocean Territory",
    "BN": "Brunei",
    "BG": "Bulgaria",
    "BF": "Burkina Faso",
    "BI": "Burundi",
    "KH": "Cambodia",
    "CM": "Cameroon",
    "CA": "Canada",
    "CV": "Cape Verde",
    "KY": "Cayman Islands",
    "CF": "Central African Republic",
    "TD": "Chad",
    "CL": "Chile",
    "CN": "China",
    "CX": "Christmas Island",
    "CC": "Cocos (Keeling) Islands",
    "CO": "Colombia",
    "KM": "Comoros",
    "CG": "Congo",
    "CK": "Cook Islands",
    "CR": "Costa Rica",
    "CI": "Cote d'Ivoire",
    "HR": "Croatia",
    "CU": "Cuba",
    "CW": "Curaçao",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DK": "Denmark",
    "DJ": "Djibouti",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "CD": "DR Congo",
    "EC": "Ecuador",
    "EG": "Egypt",
    "SV": "El Salvador",
    "GQ": "Equatorial Guinea",
    "ER": "Eritrea",
    "EE": "Estonia",
    "SZ": "Eswatini",
    "ET": "Ethiopia",
    "FK": "Falkland Islands (Malvinas)",
    "FO": "Faroe Islands",
    "FJ": "Fiji",
    "FI": "Finland",
    "FR": "France",
    "GF": "French Guiana",
    "PF": "French Polynesia",
    "GA": "Gabon",
    "GM": "Gambia",
    "GE": "Georgia",
    "DE": "Germany",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GR": "Greece",
    "GL": "Greenland",
    "GD": "Grenada",
    "GP": "Guadeloupe",
    "GU": "Guam",
    "GT": "Guatemala",
    "GG": "Guernsey",
    "GN": "Guinea",
    "GW": "Guinea-Bissau",
    "GY": "Guyana",
    "HT": "Haiti",
    "HN": "Honduras",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IS": "Iceland",
    "IN": "India",
    "ID": "Indonesia",
    "IR": "Iran",
    "IQ": "Iraq",
    "IE": "Ireland",
    "IM": "Isle of Man",
    "IL": "Israel",
    "IT": "Italy",
    "JM": "Jamaica",
    "JP": "Japan",
    "JE": "Jersey",
    "JO": "Jordan",
    "KZ": "Kazakhstan",
    "KE": "Kenya",
    "KI": "Kiribati",
    "XK": "Kosovo",
    "KW": "Kuwait",
    "KG": "Kyrgyzstan",
    "LA": "Laos",
    "LV": "Latvia",
    "LB": "Lebanon",
    "LS": "Lesotho",
    "LR": "Liberia",
    "LY": "Libya",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MO": "Macao",
    "MG": "Madagascar",
    "MW": "Malawi",
    "MY": "Malaysia",
    "MV": "Maldives",
    "ML": "Mali",
    "MT": "Malta",
    "MH": "Marshall Islands",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MU": "Mauritius",
    "YT": "Mayotte",
    "MX": "Mexico",
    "FM": "Micronesia",
    "MD": "Moldova",
    "MC": "Monaco",
    "MN": "Mongolia",
    "ME": "Montenegro",
    "MS": "Montserrat",
    "MA": "Morocco",
    "MZ": "Mozambique",
    "MM": "Myanmar",
    "NA": "Namibia",
    "NR": "Nauru",
    "NP": "Nepal",
    "NL": "Netherlands",
    "NC": "New Caledonia",
    "NZ": "New Zealand",
    "NI": "Nicaragua",
    "NE": "Niger",
    "NG": "Nigeria",
    "NU": "Niue",
    "NF": "Norfolk Island",
    "KP": "North Korea",
    "MK": "North Macedonia",
    "MP": "Northern Mariana Islands",
    "NO": "Norway",
    "OM": "Oman",
    "PK": "Pakistan",
    "PW": "Palau",
    "PA": "Panama",
    "PG": "Papua New Guinea",
    "PY": "Paraguay",
    "PE": "Peru",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "PR": "Puerto Rico",
    "QA": "Qatar",
    "RE": "Reunion",
    "RO": "Romania",
    "RU": "Russia",
    "RW": "Rwanda",
    "BL": "Saint Barthélemy",
    "SH": "Saint Helena",
    "KN": "Saint Kitts and Nevis",
    "LC": "Saint Lucia",
    "MF": "Saint Martin (French part)",
    "PM": "Saint Pierre and Miquelon",
    "VC": "Saint Vincent and the Grenadines",
    "WS": "Samoa",
    "SM": "San Marino",
    "ST": "Sao Tome and Principe",
    "SA": "Saudi Arabia",
    "SN": "Senegal",
    "RS": "Serbia",
    "SC": "Seychelles",
    "SL": "Sierra Leone",
    "SG": "Singapore",
    "SX": "Sint Maarten (Dutch part)",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "SB": "Solomon Islands",
    "SO": "Somalia",
    "ZA": "South Africa",
    "KR": "South Korea",
    "SS": "South Sudan",
    "ES": "Spain",
    "LK": "Sri Lanka",
    "PS": "State of Palestine",
    "SD": "Sudan",
    "SR": "Suriname",
    "SJ": "Svalbard and Jan Mayen",
    "SE": "Sweden",
    "CH": "Switzerland",
    "SY": "Syria",
    "TW": "Taiwan",
    "TJ": "Tajikistan",
    "TZ": "Tanzania",
    "TH": "Thailand",
    "TL": "Timor-Leste",
    "TG": "Togo",
    "TK": "Tokelau",
    "TO": "Tonga",
    "TT": "Trinidad and Tobago",
    "TN": "Tunisia",
    "TR": "Türkiye",
    "TM": "Turkmenistan",
    "TC": "Turks and Caicos Islands",
    "TV": "Tuvalu",
    "UG": "Uganda",
    "UA": "Ukraine",
    "AE": "United Arab Emirates",
    "GB": "United Kingdom",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VU": "Vanuatu",
    "VA": "Vatican City",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "VG": "Virgin Islands, British",
    "VI": "Virgin Islands, U.S.",
    "WF": "Wallis and Futuna",
    "EH": "Western Sahara",
    "YE": "Yemen",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}
_ISO_NAME_TO_CODE: dict[str, str] = {name.lower(): code for code, name in COUNTRY_NAMES.items()}

# ISO 3166-1 alpha-3 -> alpha-2, restricted to codes COUNTRY_NAMES actually
# has a name for (generated from i18n-iso-countries' getAlpha3Codes(), the
# same package jobby/utils/pipeline/countryResolver.ts already depends on,
# filtered to this file's own alpha-2 set — not hand-typed, to avoid a typo
# silently mismapping a country). Several ATS vendors' location feeds lead
# with an alpha-3 code instead of alpha-2 (see _LEADING_COUNTRY_CODE_RE
# below) — e.g. "BRA - Sao Paulo - Sao Paulo (Torre Z)" or
# "CAN-ON-Kitchener" — which nothing else in this file recognizes.
_ALPHA3_TO_ALPHA2: dict[str, str] = {
    "ABW": "AW",
    "AFG": "AF",
    "AGO": "AO",
    "AIA": "AI",
    "ALA": "AX",
    "ALB": "AL",
    "AND": "AD",
    "ARE": "AE",
    "ARG": "AR",
    "ARM": "AM",
    "ASM": "AS",
    "ATG": "AG",
    "AUS": "AU",
    "AUT": "AT",
    "AZE": "AZ",
    "BDI": "BI",
    "BEL": "BE",
    "BEN": "BJ",
    "BES": "BQ",
    "BFA": "BF",
    "BGD": "BD",
    "BGR": "BG",
    "BHR": "BH",
    "BHS": "BS",
    "BIH": "BA",
    "BLM": "BL",
    "BLR": "BY",
    "BLZ": "BZ",
    "BMU": "BM",
    "BOL": "BO",
    "BRA": "BR",
    "BRB": "BB",
    "BRN": "BN",
    "BTN": "BT",
    "BWA": "BW",
    "CAF": "CF",
    "CAN": "CA",
    "CCK": "CC",
    "CHE": "CH",
    "CHL": "CL",
    "CHN": "CN",
    "CIV": "CI",
    "CMR": "CM",
    "COD": "CD",
    "COG": "CG",
    "COK": "CK",
    "COL": "CO",
    "COM": "KM",
    "CPV": "CV",
    "CRI": "CR",
    "CUB": "CU",
    "CUW": "CW",
    "CXR": "CX",
    "CYM": "KY",
    "CYP": "CY",
    "CZE": "CZ",
    "DEU": "DE",
    "DJI": "DJ",
    "DMA": "DM",
    "DNK": "DK",
    "DOM": "DO",
    "DZA": "DZ",
    "ECU": "EC",
    "EGY": "EG",
    "ERI": "ER",
    "ESH": "EH",
    "ESP": "ES",
    "EST": "EE",
    "ETH": "ET",
    "FIN": "FI",
    "FJI": "FJ",
    "FLK": "FK",
    "FRA": "FR",
    "FRO": "FO",
    "FSM": "FM",
    "GAB": "GA",
    "GBR": "GB",
    "GEO": "GE",
    "GGY": "GG",
    "GHA": "GH",
    "GIB": "GI",
    "GIN": "GN",
    "GLP": "GP",
    "GMB": "GM",
    "GNB": "GW",
    "GNQ": "GQ",
    "GRC": "GR",
    "GRD": "GD",
    "GRL": "GL",
    "GTM": "GT",
    "GUF": "GF",
    "GUM": "GU",
    "GUY": "GY",
    "HKG": "HK",
    "HND": "HN",
    "HRV": "HR",
    "HTI": "HT",
    "HUN": "HU",
    "IDN": "ID",
    "IMN": "IM",
    "IND": "IN",
    "IOT": "IO",
    "IRL": "IE",
    "IRN": "IR",
    "IRQ": "IQ",
    "ISL": "IS",
    "ISR": "IL",
    "ITA": "IT",
    "JAM": "JM",
    "JEY": "JE",
    "JOR": "JO",
    "JPN": "JP",
    "KAZ": "KZ",
    "KEN": "KE",
    "KGZ": "KG",
    "KHM": "KH",
    "KIR": "KI",
    "KNA": "KN",
    "KOR": "KR",
    "KWT": "KW",
    "LAO": "LA",
    "LBN": "LB",
    "LBR": "LR",
    "LBY": "LY",
    "LCA": "LC",
    "LIE": "LI",
    "LKA": "LK",
    "LSO": "LS",
    "LTU": "LT",
    "LUX": "LU",
    "LVA": "LV",
    "MAC": "MO",
    "MAF": "MF",
    "MAR": "MA",
    "MCO": "MC",
    "MDA": "MD",
    "MDG": "MG",
    "MDV": "MV",
    "MEX": "MX",
    "MHL": "MH",
    "MKD": "MK",
    "MLI": "ML",
    "MLT": "MT",
    "MMR": "MM",
    "MNE": "ME",
    "MNG": "MN",
    "MNP": "MP",
    "MOZ": "MZ",
    "MRT": "MR",
    "MSR": "MS",
    "MTQ": "MQ",
    "MUS": "MU",
    "MWI": "MW",
    "MYS": "MY",
    "MYT": "YT",
    "NAM": "NA",
    "NCL": "NC",
    "NER": "NE",
    "NFK": "NF",
    "NGA": "NG",
    "NIC": "NI",
    "NIU": "NU",
    "NLD": "NL",
    "NOR": "NO",
    "NPL": "NP",
    "NRU": "NR",
    "NZL": "NZ",
    "OMN": "OM",
    "PAK": "PK",
    "PAN": "PA",
    "PER": "PE",
    "PHL": "PH",
    "PLW": "PW",
    "PNG": "PG",
    "POL": "PL",
    "PRI": "PR",
    "PRK": "KP",
    "PRT": "PT",
    "PRY": "PY",
    "PSE": "PS",
    "PYF": "PF",
    "QAT": "QA",
    "REU": "RE",
    "ROU": "RO",
    "RUS": "RU",
    "RWA": "RW",
    "SAU": "SA",
    "SDN": "SD",
    "SEN": "SN",
    "SGP": "SG",
    "SHN": "SH",
    "SJM": "SJ",
    "SLB": "SB",
    "SLE": "SL",
    "SLV": "SV",
    "SMR": "SM",
    "SOM": "SO",
    "SPM": "PM",
    "SRB": "RS",
    "SSD": "SS",
    "STP": "ST",
    "SUR": "SR",
    "SVK": "SK",
    "SVN": "SI",
    "SWE": "SE",
    "SWZ": "SZ",
    "SXM": "SX",
    "SYC": "SC",
    "SYR": "SY",
    "TCA": "TC",
    "TCD": "TD",
    "TGO": "TG",
    "THA": "TH",
    "TJK": "TJ",
    "TKL": "TK",
    "TKM": "TM",
    "TLS": "TL",
    "TON": "TO",
    "TTO": "TT",
    "TUN": "TN",
    "TUR": "TR",
    "TUV": "TV",
    "TWN": "TW",
    "TZA": "TZ",
    "UGA": "UG",
    "UKR": "UA",
    "URY": "UY",
    "USA": "US",
    "UZB": "UZ",
    "VAT": "VA",
    "VCT": "VC",
    "VEN": "VE",
    "VGB": "VG",
    "VIR": "VI",
    "VNM": "VN",
    "VUT": "VU",
    "WLF": "WF",
    "WSM": "WS",
    "XKK": "XK",
    "YEM": "YE",
    "ZAF": "ZA",
    "ZMB": "ZM",
    "ZWE": "ZW",
    # Informal/non-ISO 3-letter codes observed in real ATS feeds, not part
    # of the generated table above — added by hand because they're
    # unambiguous in context, same precedent as LOCATION_ALIASES' "uk"/"usa".
    "ROM": "RO",  # Romania — real ISO alpha-3 is ROU, but "ROM-Bucharest, PO" is observed vendor usage
}

# Lowercase-keyed alpha-3 -> alpha-2, US/CA only — reuses _ALPHA3_TO_ALPHA2
# rather than a new hand-maintained table. Lets parse_location's bare-
# token checks recognize "CAN"/"USA" the same way they already recognize
# "us"/"ca" (_BARE_ALPHA2_CODE_TO_COUNTRY) and full names
# (_ISO_NAME_TO_CODE) — confirmed live: "CAN, ON, London" left city="CAN"
# unresolved for the same reason "USA, VA, McLean" did before that fix,
# since "can"/"usa" weren't recognized as non-city tokens at all here
# (resolve_country_from_location already handles alpha-3 codes via
# _LEADING_ISO3_DASH_RE/_TRAILING_ALPHA3_RE, but those are structural,
# position-anchored patterns — not a general bare-token check the way
# _BARE_ALPHA2_CODE_TO_COUNTRY is).
_ALPHA3_US_CA_TOKENS: dict[str, str] = {
    code.lower(): alpha2 for code, alpha2 in _ALPHA3_TO_ALPHA2.items() if alpha2 in ("US", "CA")
}

# Work-mode/venue phrases that show up as the trailing token in a
# "<CountryAlias>, <ST>, <phrase>" or "<ST>, <phrase>" shape but are never
# a real city name ("USA, ID, Home Office", "USA, IA, Remote", "Utah,
# Work at Home" after _LEADING_WORD_REMOTE_SUFFIX_RE's comma insertion) —
# sampled from live pool data: "Remote" and "Home Office" together
# account for the overwhelming majority of non-city trailing tokens in
# the 3-token country-alias-first shape (92 and 63 occurrences
# respectively out of the full USA/US/CAN-prefixed sample; every other
# trailing value observed was a real city name). "Virtual"/"Work at
# Home"/"Work From Home"/"WFH" added for the same reason once the
# space-joined "<State> <remote-phrase>" shape needed the identical
# exclusion — same vocabulary as _REMOTE_KEYWORD_RE's own alternation,
# kept as a separate constant (not a regex reuse) since this needs exact-
# match set membership, not a substring search. Deliberately small and
# hand-curated rather than a broad heuristic — this only excludes the
# specific phrases confirmed live, not a guess at what "sounds like" a
# venue.
_NON_CITY_PHRASES: frozenset[str] = frozenset(
    {"remote", "home office", "virtual", "work at home", "work from home", "wfh"}
)

# Mirrors countryResolver.ts's LOCATION_ALIASES exactly.
LOCATION_ALIASES: dict[str, str] = {
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "us": "US",
    "united states of america": "US",
    "america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "uae": "AE",
    "drc": "CD",
    "ivory coast": "CI",
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "holland": "NL",
    "czechia": "CZ",
    "the netherlands": "NL",
    "bay area": "US",
    "silicon valley": "US",
    "nyc": "US",
    "new york city": "US",
}

# The subset of LOCATION_ALIASES keys that are ALSO real US/CA town
# names ("England, AR"; "Scotland, SD"; "Wales, WI"; "Holland, MI"; "New
# York City" itself) — verified against the bundled gazetteer directly
# (single-country, US/CA-only match for each). Every other
# LOCATION_ALIASES key ("usa", "us", "uk", "korea", "britain", ...) is
# never a real place name anywhere, confirmed the same way (either zero
# gazetteer matches or matches only outside US/CA) — treating those as
# potential city names in the collision guard below produced a real bug:
# "USA, VA, McLean" was reading "USA" as a possible city (since a
# distinct state token "VA" followed it) instead of recognizing "USA" as
# what it obviously is, the country. Only this narrow subset should ever
# let the collision guard suppress is_recognized_non_city.
_LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY: set[str] = {
    "england",
    "scotland",
    "wales",
    "holland",
    "new york city",
}

# Mirrors countryResolver.ts's US_STATE_TOKENS exactly.
US_STATE_TOKENS: set[str] = {
    "al",
    "alabama",
    "ak",
    "alaska",
    "az",
    "arizona",
    "ar",
    "arkansas",
    "ca",
    "california",
    "co",
    "colorado",
    "ct",
    "connecticut",
    "de",
    "delaware",
    "fl",
    "florida",
    "ga",
    "georgia",
    "hi",
    "hawaii",
    "id",
    "idaho",
    "il",
    "illinois",
    "in",
    "indiana",
    "ia",
    "iowa",
    "ks",
    "kansas",
    "ky",
    "kentucky",
    "la",
    "louisiana",
    "me",
    "maine",
    "md",
    "maryland",
    "ma",
    "massachusetts",
    "mi",
    "michigan",
    "mn",
    "minnesota",
    "ms",
    "mississippi",
    "mo",
    "missouri",
    "mt",
    "montana",
    "ne",
    "nebraska",
    "nv",
    "nevada",
    "nh",
    "new hampshire",
    "nj",
    "new jersey",
    "nm",
    "new mexico",
    "ny",
    "new york",
    "nc",
    "north carolina",
    "nd",
    "north dakota",
    "oh",
    "ohio",
    "ok",
    "oklahoma",
    "or",
    "oregon",
    "pa",
    "pennsylvania",
    "ri",
    "rhode island",
    "sc",
    "south carolina",
    "sd",
    "south dakota",
    "tn",
    "tennessee",
    "tx",
    "texas",
    "ut",
    "utah",
    "vt",
    "vermont",
    "va",
    "virginia",
    "wa",
    "washington",
    "wv",
    "west virginia",
    "wi",
    "wisconsin",
    "wy",
    "wyoming",
    "dc",
    "washington dc",
    "washington d.c.",
}

# Mirrors countryResolver.ts's CA_PROVINCE_TOKENS exactly.
CA_PROVINCE_TOKENS: set[str] = {
    "ab",
    "alberta",
    "bc",
    "british columbia",
    "mb",
    "manitoba",
    "nb",
    "new brunswick",
    "nl",
    "newfoundland and labrador",
    "ns",
    "nova scotia",
    "nt",
    "northwest territories",
    "nu",
    "nunavut",
    "on",
    "ontario",
    "pe",
    "prince edward island",
    "qc",
    "quebec",
    "sk",
    "saskatchewan",
    "yt",
    "yukon",
}

# Bare, unambiguous ISO alpha-2 country codes ("GB", "FR", "CN", "AU",
# "AM" alone, or "GB,Manchester" with no space after the comma) —
# sampled from live pool data where these simply fell through to None,
# since the only alpha-2 lookups that exist elsewhere in this file
# (US_STATE_TOKENS/CA_PROVINCE_TOKENS, LOCATION_ALIASES' hand-picked
# "us"/"uk") don't cover the other ~240 valid codes at all. Excludes
# every code that collides with a US state or CA province abbreviation
# ("CA", "DE", "IN", "MD", ... — 31 total) so this tier can never
# override the existing, deliberate state/province-wins-ties behavior
# for those; a colliding code still resolves, just via the earlier
# US/CA collision-resolution tier instead of this one, exactly as
# before this table existed. Confirmed the equivalent gap exists in
# jobby/utils/pipeline/countryResolver.ts too (i18n-iso-countries'
# getAlpha2Code resolves names, not codes, verified directly) — both
# files got this tier added together, see that file's own comment.
_BARE_ALPHA2_CODE_TO_COUNTRY: dict[str, str] = {
    code.lower(): code
    for code in COUNTRY_NAMES
    if code.lower() not in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
}

_PAREN_RE = re.compile(r"\(([^)]*)\)")
_TRAILING_STATE_RE = re.compile(r"[,-]\s*([a-z]{2})\.?\s*$")
# Trailing "<City>, <ISO3>" shape ("Bengaluru, IND", "London, GBR",
# "Tokyo, JPN") — the existing comma-tokenizer below only checks each token
# against alias/name tables, and a bare 3-letter code matches neither.
_TRAILING_ALPHA3_RE = re.compile(r"[,/]\s*([a-z]{3})\.?\s*$")

# Some ATS vendors (confirmed on AtkinsRéalis's SmartRecruiters feed) format
# location as a dot-delimited "<ISO2>.<City>.<Address>" path instead of the
# comma-separated shape every other pass in this file assumes — e.g.
# "GB.Glasgow.2 Atlantic Square York Street" or "CA.QC.Montréal.455 boul.".
# Other vendors use the same idea with "-" instead of "." and/or an alpha-3
# code instead of alpha-2 ("CAN-ON-Kitchener", "JPN-Tokyo-OVOL",
# "BRA - Sao Paulo - Sao Paulo (Torre Z)" — the last with spaces around each
# dash). Splitting on ","/"-" (the tokenizer below, and _TRAILING_STATE_RE)
# never separates a leading code glued directly to the next segment by "."
# or "-" with no comma, so it silently fell through to None even though the
# signal is unambiguous.
#
# Requiring NO space after the delimiter for the alpha-2 "." shape
# ("gb.glasgow", not "gb. glasgow") is what keeps that one from firing on an
# ordinary sentence-abbreviation prefix like "St. Louis, MO" or "Mt.
# Pleasant" — both "st"/"mt" happen to also be valid ISO codes (São Tomé,
# n/a) but are always followed by ". " (abbreviation + space), never the
# compact space-less vendor shape. This does mean a same-vendor location
# that happens to put a space after its leading code ("PE. Lima. Calle...",
# observed once) still falls through to None rather than resolving to PE —
# an accepted miss (None is this file's existing "can't confidently tell"
# contract) in exchange for never guessing wrong on the far more common
# "St./Mt./Dr." English-abbreviation shape. The alpha-3 "-" shapes don't
# have this collision risk (no common English word is "bra-", "can-",
# "jpn-", etc.), so those allow an optional space around the dash.
_LEADING_ISO2_DOT_RE = re.compile(r"^([a-z]{2})\.(?=\S)")
_LEADING_ISO3_DASH_RE = re.compile(r"^([a-z]{3})\s*-\s*(?=\S)")

# "<ISO2>-<region>-<City>-..." (e.g. "CA-QC-LONGUEUIL-J01", "AU-NSW-
# WILLIAMTOWN-001") is a *different* vendor shape from the two above: no
# space around either dash, and the region segment can be 2-3 letters or
# digits. This one is checked against the ORIGINAL (non-lowercased) string
# and requires the code and region to be ALL UPPERCASE specifically because
# a same-shaped US-domestic vendor feed also exists ("CA-Fresno-cCARE
# Clinic", "OR-Oregon-FIELD", "TX-Austin-Nucl Pharm #56") where the city
# segment is mixed/lower case — that's California/Oregon/Texas, not
# Canada/Oman/... — and merging the two would misresolve those to the wrong
# country. Requiring the region segment to be all-caps is what tells the
# two vendors apart; it is deliberately not validated as a real
# region/province code beyond that, matching this function's existing
# "structural shape is confidence enough" precedent for the alpha-2/alpha-3
# dot/dash shapes above.
_LEADING_ISO2_REGION_DASH_RE = re.compile(r"^([A-Z]{2})-[A-Z0-9]{2,3}-")

# Lowest-priority fallback: a location that is nothing but a bare city name
# ("Montreal", "Toronto", "Mumbai") with no country/province/ISO signal at
# all in the string — every other tier above legitimately returns None for
# these, since there's nothing to parse, only a name to look up.
#
# Originally generated from GeoNames' cities15000 dump (~34k rows, the
# gazetteer.py-bundled file as of authoring time — scraper/gazetteer.py
# upgraded to the larger cities1000 dump on 2026-09-19; this table is a
# static, hand-frozen snapshot with no runtime dependency on which
# gazetteer file is currently bundled, so that upgrade did not require
# re-deriving it). Built by grouping every gazetteer row by lowercased
# ascii_name and keeping only names that map to EXACTLY ONE country_code
# across the full worldwide dataset — no population-based tie-breaking,
# which a spot check showed gets real cases wrong even for "obviously
# safe" names (e.g. "Richmond" resolves to a US town over Richmond, BC by
# a slim population margin; "Georgetown" resolves to Guyana over the
# common Ontario usage). Ties are excluded entirely rather than guessed,
# preserving this function's "never guess" contract. Further filtered to
# city names actually observed in scraped job locations, then
# hand-reviewed to drop two false positives that technically have a
# single-country gazetteer match but are unsafe to trust bare: "apac" (a
# real Ugandan town, but in job postings this string is virtually always
# the Asia-Pacific acronym) and "federal" (a real Argentine town, too
# generic/administrative a word to trust without other context).
#
# To add more entries later, re-run the same derivation (now against
# cities1000, the currently-bundled file) against newly observed
# unresolved locations rather than hand-typing a new city — hand-typing
# skips the single-country-match safety check this table's entries all
# passed, and a re-derivation against the larger dataset should re-check
# every entry below too, since a name that was single-country-safe in the
# smaller 34k-row set is not guaranteed to still be safe among cities1000's
# ~171k rows.
_BARE_CITY_NAME_TO_COUNTRY: dict[str, str] = {
    "abu dhabi": "AE",
    "albacete": "ES",
    "atlanta": "US",
    "austin": "US",
    "backnang": "DE",
    "baesweiler": "DE",
    "baltimore": "US",
    "bangkok": "TH",
    "barrie": "CA",
    "basel": "CH",
    "beijing": "CN",
    "bratislava": "SK",
    "brownsville": "US",
    "bucharest": "RO",
    "budapest": "HU",
    "caen": "FR",
    "calgary": "CA",
    "cape town": "ZA",
    "carlsbad": "US",
    "catania": "IT",
    "chengdu": "CN",
    "chennai": "IN",
    "chicago": "US",
    "chongqing": "CN",
    "copenhagen": "DK",
    "dothan": "US",
    "eindhoven": "NL",
    "espoo": "FI",
    "fond du lac": "US",
    "fort erie": "CA",
    "fuzhou": "CN",
    "getafe": "ES",
    "guangzhou": "CN",
    "gurugram": "IN",
    "hangzhou": "CN",
    "hsinchu": "TW",
    "indianapolis": "US",
    "islamabad": "PK",
    "ivrea": "IT",
    "jacksonville": "US",
    "jakarta": "ID",
    "jiaxing": "CN",
    "jinan": "CN",
    "kamloops": "CA",
    "kaohsiung": "TW",
    "kelowna": "CA",
    "krakow": "PL",
    "kuala lumpur": "MY",
    "kyiv": "UA",
    "lafayette": "US",
    "lake country": "CA",
    "lehi": "US",
    "leipzig": "DE",
    "lethbridge": "CA",
    "leuven": "BE",
    "ljubljana": "SI",
    "luzhou": "CN",
    "makati city": "PH",
    "milwaukee": "US",
    "mississauga": "CA",
    "montpellier": "FR",
    "monza": "IT",
    "morrisville": "US",
    "mumbai": "IN",
    "munich": "DE",
    "neenah": "US",
    "new delhi": "IN",
    "niagara-on-the-lake": "CA",
    "noida": "IN",
    "novi": "US",
    "orlando": "US",
    "oshawa": "CA",
    "otsego": "US",
    "pasig city": "PH",
    "pattaya": "TH",
    "penzberg": "DE",
    "petaling jaya": "MY",
    "petaluma": "US",
    "phnom penh": "KH",
    "pittsburgh": "US",
    "pleasanton": "US",
    "pune": "IN",
    "puurs": "BE",
    "quezon city": "PH",
    "quito": "EC",
    "raleigh": "US",
    "red deer": "CA",
    "rennes": "FR",
    "riga": "LV",
    "salmon arm": "CA",
    "sarnia": "CA",
    "saskatoon": "CA",
    "seattle": "US",
    "seoul": "KR",
    "sepang": "MY",
    "shanghai": "CN",
    "sibiu": "RO",
    "skopje": "MK",
    "south san francisco": "US",
    "stevenage": "GB",
    "stockholm": "SE",
    "stolberg": "DE",
    "strathroy": "CA",
    "subang jaya": "MY",
    "suzhou": "CN",
    "taipei": "TW",
    "taiyuan": "CN",
    "tampa": "US",
    "targu mures": "RO",
    "tokyo": "JP",
    "toulouse": "FR",
    "tucson": "US",
    "turku": "FI",
    "ulm": "DE",
    "vaughan": "CA",
    "vilvoorde": "BE",
    "winnipeg": "CA",
    "yokohama": "JP",
}


def _matches_word(normalized: str, phrase: str) -> bool:
    escaped = re.escape(phrase)
    return re.search(rf"(?:^|[^a-z]){escaped}(?:[^a-z]|$)", normalized) is not None


_LOCATION_ALIASES_COMBINED_RE = re.compile(
    r"(?:^|[^a-z])(?:"
    + "|".join(re.escape(alias) for alias in LOCATION_ALIASES)
    + r")(?:[^a-z]|$)",
    re.IGNORECASE,
)
_COUNTRY_NAMES_COMBINED_RE = re.compile(
    r"(?:^|[^a-z])(?:"
    + "|".join(re.escape(name.lower()) for name in COUNTRY_NAMES.values())
    + r")(?:[^a-z]|$)",
    re.IGNORECASE,
)


def resolve_country_from_location(location: str | None) -> str | None:
    """Resolve a free-text job location string to an ISO alpha-2 country
    code. Returns None — never a guess — when nothing confidently matches;
    callers must treat None as "unknown," never default it to a country.

    Port of countryResolver.ts's resolveCountryFromLocation(); keep the
    matching order and alias tables identical to that file.
    """
    if not location or not location.strip():
        return None

    # "<ISO2>-<REGION>-<City>-..." vendor shape (e.g. "CA-QC-LONGUEUIL-J01")
    # is the one check that needs the ORIGINAL case (see
    # _LEADING_ISO2_REGION_DASH_RE's comment on why all-caps is what
    # distinguishes it from a same-shaped US-domestic feed) — must run
    # before the string is lowercased below.
    leading_region = _LEADING_ISO2_REGION_DASH_RE.match(location)
    if leading_region and leading_region.group(1) in COUNTRY_NAMES:
        return leading_region.group(1)

    # NFD-decompose then drop combining marks: folds "québec"/"montréal"/
    # "münchen" to their unaccented ASCII form so they match
    # CA_PROVINCE_TOKENS/_ISO_NAME_TO_CODE/LOCATION_ALIASES, whose keys are
    # all plain ASCII. Safe here specifically because this function only
    # extracts a country *signal* from the string — unlike parse_location's
    # normalized_key (identity/dedup), folding accents can never merge two
    # genuinely different places into the same resolved country by mistake,
    # it only lets an accented spelling reach a table that was already
    # reachable via its unaccented spelling.
    folded = unicodedata.normalize("NFD", location)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    normalized = folded.lower()

    leading_iso2 = _LEADING_ISO2_DOT_RE.match(normalized)
    if leading_iso2 and leading_iso2.group(1).upper() in COUNTRY_NAMES:
        return leading_iso2.group(1).upper()

    leading_iso3 = _LEADING_ISO3_DASH_RE.match(normalized)
    if leading_iso3:
        code = _ALPHA3_TO_ALPHA2.get(leading_iso3.group(1).upper())
        if code:
            return code

    paren_tokens = [m.group(1).strip() for m in _PAREN_RE.finditer(normalized)]
    without_parens = _PAREN_RE.sub(" ", normalized)
    tokens = [t.strip() for t in re.split(r"[,/|]", without_parens) if t.strip()]
    tokens += [t for t in paren_tokens if t]

    for token in tokens:
        # A handful of LOCATION_ALIASES keys are ALSO real US/CA town
        # names ("Holland, MI", "England, AR", "Scotland, SD", "Wales,
        # WI") — confirmed live: "Holland, MI" was resolving to "NL"
        # (Netherlands) via this tier, before the US/CA collision tier
        # further down ever got a chance to see "MI". Deferring here
        # when a real state/province token exists elsewhere in the
        # string mirrors parse_location's own city-extraction guard for
        # the identical ambiguity (_LOCATION_ALIASES_AMBIGUOUS_WITH_US_
        # CA_CITY) — every other LOCATION_ALIASES key ("usa", "uk",
        # "korea", ...) is never a real place name, so this never
        # affects those.
        if token in _LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY:
            other_tokens = [t for t in tokens if t != token]
            has_state_or_province_token = any(
                t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS for t in other_tokens
            )
            if has_state_or_province_token:
                continue
        code = LOCATION_ALIASES.get(token)
        if code:
            return code

    # "<City>, <CA province>, CA, <postal code>" (e.g. "London, ON, CA,
    # N6E 1V4", "Montreal, QC, CA, H3B4G7") — a trailing bare "ca" token
    # is ambiguous between California (US_STATE_TOKENS) and Canada's ISO
    # code, and the collision-resolution tier below would wrongly read it
    # as California here: since "ca" itself is also in US_STATE_TOKENS,
    # last_us_index always lands on this same trailing token, and a
    # trailing token beats an earlier one by that tier's own "prefer the
    # trailing hit" rule regardless of what the earlier CA-province token
    # was. This is a narrower, higher-confidence signal than that general
    # tier: California is never itself followed by a *different*,
    # genuine CA-province token immediately before it (California has no
    # "province" of its own to place there), so "<distinct CA province>,
    # ca" as the final two tokens unambiguously means Canada. Checked only
    # for this exact last-two-tokens shape — does not touch any other
    # "ca" occurrence, so every ordinary "<City>, CA" California case
    # (the overwhelmingly common one) is untouched.
    if len(tokens) >= 2 and tokens[-1] == "ca":
        second_to_last = tokens[-2]
        if second_to_last in CA_PROVINCE_TOKENS and second_to_last != "ca":
            return "CA"

    # A handful of CA province names / US state names are also real city
    # names in the *other* country ("Ontario, California", "Yukon,
    # Oklahoma") — scanning left-to-right and returning on the first hit
    # would read the city-name token as the jurisdiction and misclassify
    # the whole location. Collect every US/CA hit first; when tokens from
    # only one side matched, behave exactly as before (the overwhelming
    # common case — no ambiguity to resolve). When both sides matched,
    # that's the collision case: the true region token is the trailing one
    # (the "City, Region" / "City, Region, Country" convention this same
    # function already trusts elsewhere, e.g. _TRAILING_STATE_RE and
    # parse_location's tokens[-2] region extraction below), so prefer
    # whichever hit appears last in the string. Mirrors the equivalent
    # first-token-vs-distinct-token collision guard parse_location already
    # applies to city extraction, just applied here to country resolution.
    last_us_index = last_ca_index = -1
    for index, token in enumerate(tokens):
        if token in US_STATE_TOKENS:
            last_us_index = index
        if token in CA_PROVINCE_TOKENS:
            last_ca_index = index
    if last_us_index != -1 or last_ca_index != -1:
        winning_index = last_us_index if last_us_index > last_ca_index else last_ca_index
        # An explicit, full country name spelled out as its own token
        # elsewhere in the string ("China" in "Shanghai, SD, China",
        # "Netherlands" in "Amsterdam, NH, Netherlands") is a stronger
        # signal than this tier's own US/CA state/province-token guess —
        # confirmed live: both of those silently misresolved to US/CA
        # (via "SD"/"NH" respectively) even with the real country spelled
        # out right there, since this tier always returned before
        # anything downstream got a chance to see it. Safe to check
        # unconditionally (not just when the winning token happens to be
        # a US-state/CA-province/country-code collision): when the
        # explicit name and this tier's own answer agree — the
        # overwhelmingly common case, e.g. "Toronto, ON, Canada" — this
        # changes nothing, since _ISO_NAME_TO_CODE["canada"] is "CA",
        # the same answer the tier below already gives.
        for other_index, other_token in enumerate(tokens):
            if other_index == winning_index:
                continue
            explicit_country = _ISO_NAME_TO_CODE.get(other_token)
            if explicit_country:
                return explicit_country
        return "US" if last_us_index > last_ca_index else "CA"

    # Bare, non-colliding ISO alpha-2 code as its own token ("GB",
    # "GB,Manchester", "AM,Yerevan") — checked after the US/CA collision
    # tier above so a colliding code (already excluded from this table
    # anyway) can never reach here ahead of that more careful logic.
    for token in tokens:
        code = _BARE_ALPHA2_CODE_TO_COUNTRY.get(token)
        if code:
            return code

    for token in tokens:
        code = _ISO_NAME_TO_CODE.get(token)
        if code:
            return code

    if _LOCATION_ALIASES_COMBINED_RE.search(without_parens) is not None:
        for alias, code in LOCATION_ALIASES.items():
            if _matches_word(without_parens, alias):
                return code
    if _COUNTRY_NAMES_COMBINED_RE.search(without_parens) is not None:
        for code, name in COUNTRY_NAMES.items():
            if _matches_word(without_parens, name.lower()):
                return code

    trailing = _TRAILING_STATE_RE.search(without_parens.strip())
    if trailing:
        candidate = trailing.group(1)
        if candidate in US_STATE_TOKENS:
            return "US"
        if candidate in CA_PROVINCE_TOKENS:
            return "CA"

    # Trailing "<City>, <ISO3>" shape ("Bengaluru, IND", "Tokyo, JPN") — the
    # comma-tokenizer above only checks tokens against alias/name tables, so
    # a bare 3-letter code never matched anything until now.
    trailing_alpha3 = _TRAILING_ALPHA3_RE.search(without_parens.strip())
    if trailing_alpha3:
        code = _ALPHA3_TO_ALPHA2.get(trailing_alpha3.group(1).upper())
        if code:
            return code

    # Lowest-priority fallback: the whole string, once stripped, is nothing
    # but a bare city name with no country/province/ISO signal at all (e.g.
    # "Montreal", "Toronto"). Whole-string match only — not a token/substring
    # scan — so this never fires on a city name embedded in a longer string
    # ("Montreal Office" stays None; "Montreal, Canada" already resolved via
    # the name-matching tier above, long before reaching here).
    bare_city_code = _BARE_CITY_NAME_TO_COUNTRY.get(normalized.strip())
    if bare_city_code:
        return bare_city_code

    return None


# Broader than a bare "remote" match: catches the "Work at Home - Nevada" /
# "Virtual, DNK" / "US Remote - DC" shapes a real ATS emits for fully-remote
# postings that never actually say the word "remote" — sampled from live
# pool data where these were parsed but silently left is_remote=False.
_REMOTE_KEYWORD_RE = re.compile(
    r"\b(remote|virtual|work[\s-]?from[\s-]?home|wfh|work\s+at\s+home)\b", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")

# Street-address prefix glued onto a city ("200 W Orangethorpe Ave,
# Fullerton,CA 92832-2900", "8680 Beechmont Ave, Cincinnati,OH 45255-4710").
# tokens[0] in parse_location would otherwise become the street address
# instead of the city. Matches a leading run that starts with a number and
# contains a common street-suffix word, up to (but not including) the next
# comma — deliberately narrow (suffix word required) so it never eats a
# legitimate "123 Main" style city/town name that has no street suffix.
_STREET_ADDRESS_PREFIX_RE = re.compile(
    r"^\d+[\w\s.'-]*?\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|"
    r"drive|dr|lane|ln|way|parkway|pkwy|highway|hwy|circle|cir|court|ct|"
    r"place|pl|square|sq)\b\.?"
    # Optional trailing compass-direction suffix ("7000 Target Pkwy N",
    # "15800 87th St NE") — common in US street addresses, sitting
    # between the street-suffix word and the next comma. Left
    # unconsumed, this became tokens[0] on its own once the rest of the
    # prefix was stripped ("N,NCD-0375 Brooklyn Park,MN"), leaking a
    # bare direction letter into `city`. Word-boundaried so it only
    # matches a standalone direction token, never eating into a real
    # word that happens to start the same way.
    r"(?:\s+(?:n|s|e|w|ne|nw|se|sw)\b\.?)?,?\s*",
    re.IGNORECASE,
)

# Facility/store-ID token glued onto a city with no separating comma
# ("Store 2743142 Murrysville PA", "Store0187 Lexington KY"). Narrow to the
# literal "store" word plus digits so it never strips a legitimately
# city-initial numeric token this parser has no other signal about.
_STORE_ID_PREFIX_RE = re.compile(r"^store\s*#?\s*\d+\s+", re.IGNORECASE)

# Trailing "STORE - NNNN" suffix, city-first ("QUINCY STORE - 1915",
# "PICKERING STORE - 7238", "STATE BRIDGE RD STORE - 0131") — the mirror
# image of _STORE_ID_PREFIX_RE's leading shape, from a different vendor
# convention. No state/country signal is present in this shape (unlike
# the leading-store-ID case, which usually has one after the store ID),
# so this only recovers `city` — still real progress for town_resolver.py,
# which can match on a bare city name via its own name-only tier. Anchored
# to the end with the literal " STORE - " + digits sequence, so it never
# strips a legitimate mid-string "store" mention.
_TRAILING_STORE_SUFFIX_RE = re.compile(r"\s+store\s*-\s*\d+\s*$", re.IGNORECASE)

# Leading zero-padded 5-digit facility ID + dash ("02319 - Grove City
# Dialysis", "05252 - Two Rivers Dialysis", "11835 - Windermere
# Dialysis") — a different vendor convention from the "Store <id>" prefix
# above (no "store" word, and the ID is always exactly 5 digits, often
# zero-padded). Only strips the ID itself, not any brand-word suffix
# ("Dialysis", "Acute", "Office") that regularly follows the real city in
# this feed — that suffix isn't safely separable from a genuine
# multi-word city name without guessing, so it's left in `city` rather
# than risk cutting off real city text. Still real progress: the ID was
# the one piece of pure noise guaranteed to break every match, and
# leaving a "<City> Dialysis"-shaped city string is a strictly better
# input to town_resolver.py than an opaque "02319 - Grove City Dialysis".
_LEADING_FACILITY_ID_DASH_RE = re.compile(r"^\d{5}\s*-\s*")

# Trailing US ZIP / ZIP+4, or a 6-digit international postal code
# (India's PIN code, Singapore's, Vietnam's, ...) after the state/
# country token has already been captured ("Wayne, NJ, US, 07470",
# "Bangalore, Karnataka, IND, 560093", "Singapore, SG, 797546") — left in
# place, this breaks _TRAILING_STATE_RE's/_TRAILING_ALPHA3_RE's
# "...,<code>$" anchor since the string no longer ends in the real
# jurisdiction token. Confirmed live: "Bangalore, Karnataka, IND, 560093"
# stayed country_code=None even though "IND" alone (no trailing digits)
# resolves correctly — the 6-digit PIN code broke the alpha-3 match the
# same way a 5-digit US ZIP breaks the 2-letter state match. Stripped
# from the end only, never mid string, so it can't accidentally eat a
# real 5/6-digit town/suite identifier elsewhere in the string.
_TRAILING_ZIP_RE = re.compile(r"[,\s]+\d{5}(?:-\d{4})?\s*$|[,\s]+\d{6}\s*$")

# Trailing short (1-4 digit) facility/store code after the state token,
# space-separated rather than comma-separated ("Fayetteville, NC 0388",
# "Winchester, KY 0464", "League City, TX 2821", "Saratoga Springs, NY
# 0560") — same failure mode as the 5-digit ZIP case above (breaks the
# "...,<state>$" trailing-token match), just a shorter code. Requires a
# space (not comma) before the digits specifically so it never touches an
# already-correct "<City>, <ST>, <4-digit-something>" comma-separated
# shape — those have their own, already-working tokenization and this
# must not interfere with it. 5-digit is deliberately excluded here (that
# is _TRAILING_ZIP_RE's job, run first) so the two never double-strip or
# disagree on where a boundary is.
_TRAILING_SHORT_CODE_RE = re.compile(r"(?<=[A-Za-z])\s+\d{1,4}\s*$")

# Trailing "<ST> - <suffix>" after the LAST comma ("New Haven, CT - USA",
# "Dallas, TX - Data Center", "Charlotte, NC - Whitehall Park Dr") — the
# dash-glued suffix means tokens[-1] becomes "ct - usa" instead of the
# bare state code the 2-token/N-token region-extraction tiers need to
# see. Anchored to fire only after the string's final comma (via the
# lookbehind requiring "," immediately before the state code, allowing
# only spaces in between) specifically so it never touches a city name
# that itself contains a dash before any comma ("Winston- Salem, NC -
# USA" must still read "Winston- Salem" as the city, untouched — only
# the segment after the LAST comma is a candidate here). The captured
# state token itself is validated against US_STATE_TOKENS/
# CA_PROVINCE_TOKENS by the caller before this substitution is trusted,
# not by this regex.
_TRAILING_STATE_DASH_SUFFIX_RE = re.compile(r",\s*([A-Za-z]{2})\s+-\s+[^,]+$")

# "<City>-<FullStateName>(<zip>)" — no comma or space around the dash at
# all, trailing zip in parens ("Laredo-Texas(78043)", "Dallas-
# Texas(75216)", "College Station-Texas(77845)"), a distinct ATS vendor
# shape from every other dash pattern in this file (those all have a
# space around the dash, or the state segment first). 81 rows sampled.
# The city segment is greedy-minimal up to the LAST dash so a
# multi-word city like "College Station" is captured whole rather than
# split at its own internal space; the state segment is validated
# against US_STATE_TOKENS/CA_PROVINCE_TOKENS by the caller, same
# "regex finds the shape, a table lookup decides whether to trust it"
# split as every other cleanup pattern here.
_TRAILING_DASH_STATE_PAREN_ZIP_RE = re.compile(
    r"^(.+)-([A-Za-z][A-Za-z ]*?)\(\d+\)\s*$"
)

# Trailing Canadian postal code ("London, ON, CA, N6E 1V4", "Montreal, QC,
# CA, H3B4G7") — letter-digit-letter [optional space] digit-letter-digit,
# the fixed Canada Post format. Same purpose as _TRAILING_ZIP_RE: strip it
# so the string ends in the real jurisdiction token ("CA") instead, which
# is what the CA-province-collision tier in resolve_country_from_location
# needs to see. Anchored to the end only, same reasoning as the US ZIP
# pattern above.
_TRAILING_CA_POSTAL_CODE_RE = re.compile(
    r"[,\s]+[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d\s*$"
)

# Trailing facility code stuck onto the end of a parenthetical, after the
# closing paren ("W. Jefferson, NC (W Jefferson) 2255", "Warwick, RI (N
# Warwick) 2397", "Chandler, AZ (W Chandler) 0674"). _PAREN_RE strips the
# parenthetical's *contents* but not this trailing digit run — left in
# place, "NC (W Jefferson) 2255" collapses to tokens[-1] == "nc   2255"
# once the parens are gone, which fails the exact "last_lower in
# US_STATE_TOKENS" membership check even though the real state token (NC)
# is sitting right there. Digits only (no letters), so this never eats a
# trailing word.
_TRAILING_PAREN_CODE_RE = re.compile(r"\)\s*\d+\s*$")

# Space-joined "<City words> <ST>" with no comma at all ("Portland OR",
# "Store 2743142 Murrysville PA" after store-ID stripping) — the existing
# tokenizer below only ever splits on commas, so a whole such string
# becomes one opaque tokens[0] and neither city nor region is extracted,
# even though the trailing 2-letter token is an unambiguous US-state/
# CA-province abbreviation. Rather than teach the tokenizer a second,
# space-based splitting mode, insert the comma the string is missing so
# every downstream tier (city extraction, region extraction, country
# resolution) runs completely unchanged. Requires: (a) the token is
# ALL-CAPS in the original string — lowercase/mixed-case two-letter words
# ("in", "or", "hi") are common English words, not state codes, and this
# must not fire on "Now Hiring in" or "Lakes or Rivers"-style noise; (b)
# no comma anywhere in the string already — a string that already uses
# commas has its own, already-correct tokenization and must not be
# touched; (c) preceded by whitespace and at least one letter, so a bare
# "OR" or a code glued to digits ("2743142OR") is never split.
_TRAILING_SPACE_STATE_RE = re.compile(r"(?<=[A-Za-z])\s+([A-Z]{2})\s*$")

# Leading "<ST> - <City>" / "<ST>-<City>" ("WV - Triadelphia, 215 Cabela Dr
# - Retail XFR2716", "CT-WALLINGFORD, 108 LEIGUS RD", "WA - Fife",
# "NC-Rocky Mount-PAM Specialty Hospital"). A documented, deliberately
# unhandled ambiguity in resolve_country_from_location itself (see
# _LEADING_ISO2_REGION_DASH_RE's comment: it requires the whole
# "<code>-<region>-<city>" shape to be ALL-CAPS specifically to exclude
# this exact mixed-case "<state>-<city>" shape, since a same-shaped
# ISO2-country vendor feed also exists and the two would otherwise
# misresolve into each other). Handled here instead, narrowly: reorders
# to the "<City>, <ST>" shape every downstream tier already understands,
# rather than teaching resolve_country_from_location a second reading of
# the same leading-dash structure. Requires the same ALL-CAPS-token
# guard as the trailing case above (state code only, never a common
# lowercase word), and the city segment (up to the next comma or a
# second dash) must contain a letter, so a bare "WV -" or "WV - 12345"
# with no real city text is left untouched.
_LEADING_SPACE_STATE_DASH_RE = re.compile(
    r"^([A-Z]{2})\s*-\s*([A-Za-z][^,-]*)"
)

# Leading full state/province name + dash ("Idaho - Boise", "Kansas -
# Great Bend") — same shape and purpose as _LEADING_SPACE_STATE_DASH_RE,
# just a full name instead of a 2-letter code. No ALL-CAPS guard needed
# here (unlike the 2-letter case): a full state name has no same-shaped
# ISO-country-code collision risk to exclude, since resolve_country_from_
# location has no "<full word>-<City>" ATS vendor tier this could be
# confused with. Case-insensitive on the captured segment itself; the
# membership check against US_STATE_TOKENS/CA_PROVINCE_TOKENS (which are
# all-lowercase keys) happens in Python, not in this regex.
_LEADING_WORD_DASH_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*-\s*([A-Za-z][^,-]*)")

# Leading full state/province name + trailing remote-phrase, space-joined
# with no dash or comma at all ("Utah Work at Home", "Oregon Virtual",
# "Tennessee Work at Home", "West Virginia Work at Home") — a real,
# fairly common ATS shape (60 rows sampled) distinct from the dash-joined
# "<ST> - Remote" case _LEADING_SPACE_STATE_DASH_RE/_LEADING_WORD_DASH_RE
# already handle. Anchored on the remote-phrase being the trailing,
# whole-string suffix (via _REMOTE_KEYWORD_RE's own alternation, reused
# here rather than duplicated) so the leading segment captured in group 1
# is whatever comes before it; that segment is then validated against
# US_STATE_TOKENS/CA_PROVINCE_TOKENS in Python before any comma is
# inserted, same "regex finds the shape, a table membership check decides
# whether to trust it" split as every other cleanup pattern in this file.
_LEADING_WORD_REMOTE_SUFFIX_RE = re.compile(
    r"^([A-Za-z][A-Za-z ]*?)\s+"
    r"(remote|virtual|work[\s-]?from[\s-]?home|wfh|work\s+at\s+home)\s*$",
    re.IGNORECASE,
)

_US_CA_COUNTRY_COLLISION_CODES = {c.lower() for c in COUNTRY_NAMES} & (
    US_STATE_TOKENS | CA_PROVINCE_TOKENS
)

# (city.casefold(), collision_code.lower()) -> the real country, for cities
# whose parsed region happens to be a US-state/CA-province abbreviation
# that ALSO collides with a different country's ISO code ("Bangalore, IN"
# resolves region="IN" correctly as a US-state-shaped token, but IN here
# means India, not Indiana — the same ambiguity _leading_collision_code_
# has_explicit_country_elsewhere handles for an explicit country NAME
# elsewhere in the string, this table handles for the more common case
# where only the city name itself is the disambiguating signal).
#
# Derived the same way as _BARE_CITY_NAME_TO_COUNTRY (see that table's
# comment for the full method): for each (city, collision_code) pair
# observed in real unmatched pool data (covering BOTH US-collision codes
# like "in"/"de" resolved as country_code="US", and CA-province-collision
# codes like "pe"/"nl"/"sk" resolved as country_code="CA" — e.g. "Lima,
# PE" was misresolving to Canada via Prince Edward Island's "pe" before
# this second pass covered it), kept only when (a) no real town named
# `city` exists in the US OR CA jurisdiction that collision_code would
# otherwise mean (ruling out that reading being correct — e.g. this
# table has no ("earth city", "mo") entry, since Earth City, Missouri is
# a real town and MO doesn't collide with any country code anyway; the
# codes that DO collide, like "in"/"de"/"pe"/"nl", still get an entry
# excluded whenever a matching US/CA town exists), and (b) exactly one
# gazetteer town named `city` exists in the collided-with country (never
# a tie, same "never guess" contract as every other table in this file).
# Re-run the same derivation against fresh unresolved-location data to
# add more entries — do not hand-type new ones, for the same
# safety-check reason _BARE_CITY_NAME_TO_COUNTRY's own comment gives.
_CITY_REGION_COLLISION_TO_COUNTRY: dict[tuple[str, str], str] = {
    ("'s-hertogenbosch", "nl"): "NL",
    ("aalsmeer", "nl"): "NL",
    ("ahmedabad", "in"): "IN",
    ("ahrensburg", "de"): "DE",
    ("albersweiler", "de"): "DE",
    ("alblasserdam", "nl"): "NL",
    ("aldersbach", "de"): "DE",
    ("alkmaar", "nl"): "NL",
    ("almelo", "nl"): "NL",
    ("almere", "nl"): "NL",
    ("alphen aan den rijn", "nl"): "NL",
    ("altentreptow", "de"): "DE",
    ("amersfoort", "nl"): "NL",
    ("ammerzoden", "nl"): "NL",
    ("ampfing", "de"): "DE",
    ("amstelveen", "nl"): "NL",
    ("amsterdam", "nl"): "NL",
    ("arequipa", "pe"): "PE",
    ("arnhem", "nl"): "NL",
    ("arnsberg", "de"): "DE",
    ("aschaffenburg", "de"): "DE",
    ("aschheim", "de"): "DE",
    ("assamstadt", "de"): "DE",
    ("augsburg", "de"): "DE",
    ("bad arolsen", "de"): "DE",
    ("bad bentheim", "de"): "DE",
    ("bad camberg", "de"): "DE",
    ("bad freienwalde", "de"): "DE",
    ("bad kissingen", "de"): "DE",
    ("bad lauterberg", "de"): "DE",
    ("bad segeberg", "de"): "DE",
    ("baku", "az"): "AZ",
    ("balikpapan", "id"): "ID",
    ("banda del rio sali", "ar"): "AR",
    ("bangalore", "in"): "IN",
    ("barneveld", "nl"): "NL",
    ("barranquilla", "co"): "CO",
    ("barrie", "ca"): "CA",
    ("bautzen", "de"): "DE",
    ("bayreuth", "de"): "DE",
    ("beesd", "nl"): "NL",
    ("beeskow", "de"): "DE",
    ("bekasi", "id"): "ID",
    ("belm", "de"): "DE",
    ("bengaluru", "in"): "IN",
    ("bergkamen", "de"): "DE",
    ("berkel en rodenrijs", "nl"): "NL",
    ("berlin", "de"): "DE",
    ("bhiwadi", "in"): "IN",
    ("bhubaneshwar", "in"): "IN",
    ("biessenhofen", "de"): "DE",
    ("bochum", "de"): "DE",
    ("bonaventure", "ca"): "CA",
    ("bonn", "de"): "DE",
    ("boucherville", "ca"): "CA",
    ("bratislava", "sk"): "SK",
    ("braunschweig", "de"): "DE",
    ("breda", "nl"): "NL",
    ("breitnau", "de"): "DE",
    ("bremen", "de"): "DE",
    ("bremerhaven", "de"): "DE",
    ("bromont", "ca"): "CA",
    ("bucaramanga", "co"): "CO",
    ("buenos aires", "ar"): "AR",
    ("burgbernheim", "de"): "DE",
    ("burghausen", "de"): "DE",
    ("burnaby", "ca"): "CA",
    ("cajamarca", "pe"): "PE",
    ("calgary", "ca"): "CA",
    ("cali", "co"): "CO",
    ("callao", "pe"): "PE",
    ("cartagena", "co"): "CO",
    ("casablanca", "ma"): "MA",
    ("castrop-rauxel", "de"): "DE",
    ("chengalpattu", "in"): "IN",
    ("chennai", "in"): "IN",
    ("chisinau", "md"): "MD",
    ("ciudad de panama", "pa"): "PA",
    ("cochem", "de"): "DE",
    ("coimbatore", "in"): "IN",
    ("cookstown", "ca"): "CA",
    ("cottbus", "de"): "DE",
    ("dachau", "de"): "DE",
    ("dartmouth", "ca"): "CA",
    ("deggendorf", "de"): "DE",
    ("delft", "nl"): "NL",
    ("demmin", "de"): "DE",
    ("den bosch", "nl"): "NL",
    ("den haag", "nl"): "NL",
    ("den helder", "nl"): "NL",
    ("deventer", "nl"): "NL",
    ("dordrecht", "nl"): "NL",
    ("dorsten", "de"): "DE",
    ("dortmund", "de"): "DE",
    ("dresden", "de"): "DE",
    ("drunen", "nl"): "NL",
    ("duesseldorf", "de"): "DE",
    ("duisburg", "de"): "DE",
    ("dusseldorf", "de"): "DE",
    ("ebersberg", "de"): "DE",
    ("eggenfelden", "de"): "DE",
    ("eindhoven", "nl"): "NL",
    ("eislingen", "de"): "DE",
    ("emmen", "nl"): "NL",
    ("erding", "de"): "DE",
    ("erlangen", "de"): "DE",
    ("eschborn", "de"): "DE",
    ("essenbach", "de"): "DE",
    ("etobicoke", "ca"): "CA",
    ("euskirchen", "de"): "DE",
    ("faridabad", "in"): "IN",
    ("fez", "ma"): "MA",
    ("floriana", "mt"): "MT",
    ("fockbek", "de"): "DE",
    ("frankfurt am main", "de"): "DE",
    ("frankfurt/oder", "de"): "DE",
    ("frechen", "de"): "DE",
    ("freiburg im breisgau", "de"): "DE",
    ("freilassing", "de"): "DE",
    ("fuchsstadt", "de"): "DE",
    ("funza", "co"): "CO",
    ("gaanderen", "nl"): "NL",
    ("galanta", "sk"): "SK",
    ("geertruidenberg", "nl"): "NL",
    ("gelsenkirchen", "de"): "DE",
    ("gennep", "nl"): "NL",
    ("gerlingen", "de"): "DE",
    ("germersheim", "de"): "DE",
    ("ghaziabad", "in"): "IN",
    ("gifhorn", "de"): "DE",
    ("gladbeck", "de"): "DE",
    ("gorinchem", "nl"): "NL",
    ("grafenrheinfeld", "de"): "DE",
    ("gransee", "de"): "DE",
    ("grasbrunn", "de"): "DE",
    ("greifswald", "de"): "DE",
    ("grenzach-wyhlen", "de"): "DE",
    ("groningen", "nl"): "NL",
    ("gross-gerau", "de"): "DE",
    ("grossbeeren", "de"): "DE",
    ("grossheubach", "de"): "DE",
    ("guaymallen", "ar"): "AR",
    ("gunzenhausen", "de"): "DE",
    ("gurgaon", "in"): "IN",
    ("gurugram", "in"): "IN",
    ("haifa", "il"): "IL",
    ("haiger", "de"): "DE",
    ("halifax", "ca"): "CA",
    ("halton hills", "ca"): "CA",
    ("hamburg", "de"): "DE",
    ("hanau", "de"): "DE",
    ("hannover", "de"): "DE",
    ("harsefeld", "de"): "DE",
    ("hasselt", "nl"): "NL",
    ("heerenveen", "nl"): "NL",
    ("heilbronn", "de"): "DE",
    ("heiligengrabe", "de"): "DE",
    ("helmstedt", "de"): "DE",
    ("hemmingstedt", "de"): "DE",
    ("hennigsdorf", "de"): "DE",
    ("herzberg am harz", "de"): "DE",
    ("herzogenaurach", "de"): "DE",
    ("hilden", "de"): "DE",
    ("hillsdale", "ca"): "CA",
    ("hilter", "de"): "DE",
    ("hirschaid", "de"): "DE",
    ("hlohovec", "sk"): "SK",
    ("hohen neuendorf", "de"): "DE",
    ("hohenwarsleben", "de"): "DE",
    ("holon", "il"): "IL",
    ("homburg", "de"): "DE",
    ("hoofddorp", "nl"): "NL",
    ("hoogvliet", "nl"): "NL",
    ("horst", "nl"): "NL",
    ("hosur", "in"): "IN",
    ("hyderabad", "in"): "IN",
    ("ica", "pe"): "PE",
    ("idar-oberstein", "de"): "DE",
    ("ilo", "pe"): "PE",
    ("ingolstadt", "de"): "DE",
    ("ismaning", "de"): "DE",
    ("jaipur", "in"): "IN",
    ("jakarta", "id"): "ID",
    ("joure", "nl"): "NL",
    ("kampen", "nl"): "NL",
    ("kappelrodeck", "de"): "DE",
    ("karawang", "id"): "ID",
    ("karlsruhe", "de"): "DE",
    ("kassel", "de"): "DE",
    ("kempten", "de"): "DE",
    ("kenitra", "ma"): "MA",
    ("kerkrade", "nl"): "NL",
    ("kiryat gat", "il"): "IL",
    ("kitimat", "ca"): "CA",
    ("kitzingen", "de"): "DE",
    ("koblenz", "de"): "DE",
    ("kochi", "in"): "IN",
    ("koeln", "de"): "DE",
    ("kolbermoor", "de"): "DE",
    ("kolkata", "in"): "IN",
    ("konz", "de"): "DE",
    ("kosice", "sk"): "SK",
    ("krefeld", "de"): "DE",
    ("krupina", "sk"): "SK",
    ("kulmbach", "de"): "DE",
    ("la pocatiere", "ca"): "CA",
    ("laatzen", "de"): "DE",
    ("labrador city", "ca"): "CA",
    ("lahr", "de"): "DE",
    ("lampertheim", "de"): "DE",
    ("landshut", "de"): "DE",
    ("langelsheim", "de"): "DE",
    ("langley", "ca"): "CA",
    ("laval", "ca"): "CA",
    ("leinfelden-echterdingen", "de"): "DE",
    ("leipzig", "de"): "DE",
    ("lelystad", "nl"): "NL",
    ("levice", "sk"): "SK",
    ("levis", "ca"): "CA",
    ("lim", "pe"): "PE",
    ("lima", "pe"): "PE",
    ("limburgerhof", "de"): "DE",
    ("longueuil", "ca"): "CA",
    ("lorch", "de"): "DE",
    ("ludhiana", "in"): "IN",
    ("ludwigshafen", "de"): "DE",
    ("ludwigshafen am rhein", "de"): "DE",
    ("ludwigslust", "de"): "DE",
    ("luedinghausen", "de"): "DE",
    ("maarssen", "nl"): "NL",
    ("maasbracht", "nl"): "NL",
    ("maasdijk", "nl"): "NL",
    ("magdeburg", "de"): "DE",
    ("malchin", "de"): "DE",
    ("mangalore", "in"): "IN",
    ("mannheim", "de"): "DE",
    ("mar del plata", "ar"): "AR",
    ("markdorf", "de"): "DE",
    ("markham", "ca"): "CA",
    ("marktheidenfeld", "de"): "DE",
    ("medellin", "co"): "CO",
    ("meerane", "de"): "DE",
    ("megrine", "tn"): "TN",
    ("meknes", "ma"): "MA",
    ("melsungen", "de"): "DE",
    ("meppel", "nl"): "NL",
    ("metzingen", "de"): "DE",
    ("michalovce", "sk"): "SK",
    ("mirabel", "ca"): "CA",
    ("mississauga", "ca"): "CA",
    ("moerdijk", "nl"): "NL",
    ("monheim am rhein", "de"): "DE",
    ("montreal", "ca"): "CA",
    ("moquegua", "pe"): "PE",
    ("muelheim-kaerlich", "de"): "DE",
    ("muenchen", "de"): "DE",
    ("mumbai", "in"): "IN",
    ("munich", "de"): "DE",
    ("mysore", "in"): "IN",
    # Manually added, not auto-derived: GeoNames' cities1000 dump has no
    # "München"-named row for Munich at all (its `name` field is
    # literally the English exonym "Munich", and neither "münchen" nor
    # its accent-folded "munchen" appear in alternate_names either) — so
    # the automated derivation's alternate_names cross-reference could
    # never find this spelling. Verified against the live gazetteer
    # directly before adding — see this table's own comment for why
    # hand-typing is normally unsafe; "münchen"/"munich" mean the exact
    # same single, unambiguous German city, so this one is a verified
    # exception, not a guess.
    ("münchen", "de"): "DE",
    ("naila", "de"): "DE",
    ("nanjangud", "in"): "IN",
    ("navi mumbai", "in"): "IN",
    ("nederweert", "nl"): "NL",
    ("neu-isenburg", "de"): "DE",
    ("neu-ulm", "de"): "DE",
    ("neubukow", "de"): "DE",
    ("neuenstein", "de"): "DE",
    ("neumunster", "de"): "DE",
    ("neuquen", "ar"): "AR",
    ("neuss", "de"): "DE",
    ("niederzier", "de"): "DE",
    ("nienburg/weser", "de"): "DE",
    ("nijkerk", "nl"): "NL",
    ("nijmegen", "nl"): "NL",
    ("nitra", "sk"): "SK",
    ("noida", "in"): "IN",
    ("nunspeet", "nl"): "NL",
    ("nuth", "nl"): "NL",
    ("oldenburg in holstein", "de"): "DE",
    ("oss", "nl"): "NL",
    ("osthofen", "de"): "DE",
    ("ostrhauderfehn", "de"): "DE",
    ("paderborn", "de"): "DE",
    ("patiala", "in"): "IN",
    ("penzberg", "de"): "DE",
    ("petah tikva", "il"): "IL",
    ("pezinok", "sk"): "SK",
    ("pfaffenhofen an der ilm", "de"): "DE",
    ("pithampur", "in"): "IN",
    ("plaidt", "de"): "DE",
    ("pocito", "ar"): "AR",
    ("ponda", "in"): "IN",
    ("poprad", "sk"): "SK",
    ("port hardy", "ca"): "CA",
    ("prenzlau", "de"): "DE",
    ("prievidza", "sk"): "SK",
    ("pulheim", "de"): "DE",
    ("pullach im isartal", "de"): "DE",
    ("pune", "in"): "IN",
    ("qiryat gat", "il"): "IL",
    ("qormi", "mt"): "MT",
    ("quickborn", "de"): "DE",
    ("ra'anana", "il"): "IL",
    ("rabat", "ma"): "MA",
    ("radeberg", "de"): "DE",
    ("rafaela", "ar"): "AR",
    ("rathenow", "de"): "DE",
    ("ratingen", "de"): "DE",
    ("recklinghausen", "de"): "DE",
    ("regen", "de"): "DE",
    ("regensburg", "de"): "DE",
    ("remscheid", "de"): "DE",
    ("rendsburg", "de"): "DE",
    ("rijnsburg", "nl"): "NL",
    ("rimouski", "ca"): "CA",
    ("roermond", "nl"): "NL",
    ("rostock", "de"): "DE",
    ("rotterdam", "nl"): "NL",
    ("rottweil", "de"): "DE",
    ("rouyn-noranda", "ca"): "CA",
    ("rudolstadt", "de"): "DE",
    ("saffig", "de"): "DE",
    ("saguenay", "ca"): "CA",
    ("sailauf", "de"): "DE",
    ("saint-bruno", "ca"): "CA",
    ("salzgitter", "de"): "DE",
    ("san isidro", "pe"): "PE",
    ("sanand", "in"): "IN",
    ("santiago de surco", "pe"): "PE",
    ("sassenheim", "nl"): "NL",
    ("schiedam", "nl"): "NL",
    ("schmallenberg", "de"): "DE",
    ("schwaebisch gmuend", "de"): "DE",
    ("schwandorf", "de"): "DE",
    ("schwarzheide", "de"): "DE",
    ("schweinfurt", "de"): "DE",
    ("schwerin", "de"): "DE",
    ("sderot", "il"): "IL",
    ("seelow", "de"): "DE",
    ("senica", "sk"): "SK",
    ("siegen", "de"): "DE",
    ("sigmaringen", "de"): "DE",
    ("sindelfingen", "de"): "DE",
    ("singen", "de"): "DE",
    ("sitarganj", "in"): "IN",
    ("skalica", "sk"): "SK",
    ("soest", "de"): "DE",
    ("st laurent", "ca"): "CA",
    ("st. leon-rot", "de"): "DE",
    ("suhl", "de"): "DE",
    ("tamm", "de"): "DE",
    ("tanger", "ma"): "MA",
    ("tangerang", "id"): "ID",
    ("tangiers", "ma"): "MA",
    ("taunusstein", "de"): "DE",
    ("tel aviv", "il"): "IL",
    ("tel aviv-yafo", "il"): "IL",
    ("teltow", "de"): "DE",
    ("tenjo", "co"): "CO",
    ("the hague", "nl"): "NL",
    ("tiel", "nl"): "NL",
    ("tilburg", "nl"): "NL",
    ("tilbury", "ca"): "CA",
    ("tirane", "al"): "AL",
    ("torgelow", "de"): "DE",
    ("trenque lauquen", "ar"): "AR",
    ("trier", "de"): "DE",
    ("trnava", "sk"): "SK",
    ("tuttlingen", "de"): "DE",
    ("uelzen", "de"): "DE",
    ("uithoorn", "nl"): "NL",
    ("ulm", "de"): "DE",
    ("untergruppenbach", "de"): "DE",
    ("unterschleissheim", "de"): "DE",
    ("utrecht", "nl"): "NL",
    ("vaassen", "nl"): "NL",
    ("val-d'or", "ca"): "CA",
    ("vaughan", "ca"): "CA",
    ("veenendaal", "nl"): "NL",
    ("veghel", "nl"): "NL",
    ("veitsbronn", "de"): "DE",
    ("venlo", "nl"): "NL",
    ("venray", "nl"): "NL",
    ("vernon", "ca"): "CA",
    ("waddinxveen", "nl"): "NL",
    ("waldshut-tiengen", "de"): "DE",
    ("weiden", "de"): "DE",
    ("wertheim", "de"): "DE",
    ("wesel", "de"): "DE",
    ("wesseling", "de"): "DE",
    ("wetzlar", "de"): "DE",
    ("whitby", "ca"): "CA",
    ("wilsdruff", "de"): "DE",
    ("wolgast", "de"): "DE",
    ("wuppertal", "de"): "DE",
    ("wustermark", "de"): "DE",
    ("yokneam", "il"): "IL",
    ("zell im wiesental", "de"): "DE",
    ("zeven", "de"): "DE",
    ("zevenaar", "nl"): "NL",
    ("zilina", "sk"): "SK",
    ("zoetermeer", "nl"): "NL",
    ("zundert", "nl"): "NL",
    ("zvolen", "sk"): "SK",
    ("zwolle", "nl"): "NL",
}


def export_location_tables() -> dict[str, object]:
    """Hand-authored lookup tables, as plain JSON-serializable data.

    Used by scripts/generate_country_resolver_ts.py to regenerate
    jobby/utils/pipeline/generated/country-resolver-data.ts — the TS
    resolver's only source for these tables, so the two can't drift the
    way they did repeatedly by hand (e.g. a fix landing in
    _CITY_REGION_COLLISION_TO_COUNTRY here and being missed in
    countryResolver.ts's hand-typed copy).

    Only the hand-authored tables are exported. Several other tables in
    this file (_ISO_NAME_TO_CODE, _ALPHA3_US_CA_TOKENS,
    _US_CA_COUNTRY_COLLISION_CODES, _BARE_ALPHA2_CODE_TO_COUNTRY) are
    derived from these at import time via comprehensions — TS
    independently re-derives its own equivalents the same way from its
    copy of COUNTRY_NAMES/US_STATE_TOKENS/CA_PROVINCE_TOKENS, so they
    don't need generating separately.

    The matching-tier *logic* (resolve_country_from_location's tiered
    checks, parse_location's city/region extraction) is NOT exported —
    only the data. TS's own implementation of that logic is still a
    separate, hand-ported file; keep it in sync by hand as before.
    """
    return {
        "country_names": COUNTRY_NAMES,
        "location_aliases": LOCATION_ALIASES,
        "location_aliases_ambiguous_with_us_ca_city": sorted(
            _LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY
        ),
        "us_state_tokens": sorted(US_STATE_TOKENS),
        "ca_province_tokens": sorted(CA_PROVINCE_TOKENS),
        "non_city_phrases": sorted(_NON_CITY_PHRASES),
        "bare_city_name_to_country": _BARE_CITY_NAME_TO_COUNTRY,
        # Tuple keys aren't JSON-safe — flatten to the same "city|code"
        # string key countryResolver.ts already hand-typed its own copy
        # with, so the generated TS table needs zero shape translation
        # at the call site.
        "city_region_collision_to_country": {
            f"{city}|{code}": country
            for (city, code), country in _CITY_REGION_COLLISION_TO_COUNTRY.items()
        },
    }


def _leading_collision_code_has_explicit_country_elsewhere(
    leading_code: str, rest_of_string: str
) -> bool:
    """True when leading_code is a US-state/CA-province collision code
    ("de", "in", "ca", ...) AND rest_of_string already spells out a real
    country name as its own comma-separated token ("Germany" after "DE").

    Used by both leading-dash branches in _clean_location_for_parsing to
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
    if leading_code.lower() not in _US_CA_COUNTRY_COLLISION_CODES:
        return False
    return any(
        t.strip().lower() in _ISO_NAME_TO_CODE for t in rest_of_string.split(",") if t.strip()
    )


def _clean_location_for_parsing(raw: str) -> str:
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
    dash_state_paren_zip = _TRAILING_DASH_STATE_PAREN_ZIP_RE.match(cleaned)
    if dash_state_paren_zip and dash_state_paren_zip.group(2).strip().lower() in (
        US_STATE_TOKENS | CA_PROVINCE_TOKENS
    ):
        city_segment = dash_state_paren_zip.group(1).strip()
        state_segment = dash_state_paren_zip.group(2).strip()
        cleaned = f"{city_segment}, {state_segment}"

    cleaned = _TRAILING_PAREN_CODE_RE.sub(")", cleaned)
    cleaned = _TRAILING_ZIP_RE.sub("", cleaned)
    cleaned = _TRAILING_CA_POSTAL_CODE_RE.sub("", cleaned)
    cleaned = _TRAILING_SHORT_CODE_RE.sub("", cleaned)

    state_dash_suffix = _TRAILING_STATE_DASH_SUFFIX_RE.search(cleaned)
    if state_dash_suffix and state_dash_suffix.group(1).lower() in (
        US_STATE_TOKENS | CA_PROVINCE_TOKENS
    ):
        # Discards the suffix (e.g. "Remote" in "Atlanta, GA - Remote"),
        # which would silently lose is_remote if that were still computed
        # from this cleaned string — it isn't: parse_location computes
        # is_remote from the untouched raw string instead, specifically
        # so cleanup steps like this one can never suppress that signal.
        cleaned = cleaned[: state_dash_suffix.start()] + f", {state_dash_suffix.group(1)}"

    cleaned = _STREET_ADDRESS_PREFIX_RE.sub("", cleaned)
    cleaned = _STORE_ID_PREFIX_RE.sub("", cleaned)
    cleaned = _TRAILING_STORE_SUFFIX_RE.sub("", cleaned)
    cleaned = _LEADING_FACILITY_ID_DASH_RE.sub("", cleaned)

    # Skip when the more specific "<ISO2>-<REGION>-<City>-..." ATS vendor
    # shape (all-caps region segment, e.g. "CA-QC-LONGUEUIL-J01") already
    # matches — that's resolve_country_from_location's own, more precise
    # reading of a leading "<2 letters>-" prefix, and reordering here
    # first would garble the exact structure it depends on. Also skip via
    # _leading_collision_code_has_explicit_country_elsewhere — see that
    # helper's docstring for the "DE - Berlin, Germany" case this guards.
    leading = _LEADING_SPACE_STATE_DASH_RE.match(cleaned)
    if (
        leading
        and leading.group(1).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
        and not _LEADING_ISO2_REGION_DASH_RE.match(cleaned)
    ):
        city_segment = leading.group(2).strip()
        rest = cleaned[leading.end():]
        if _leading_collision_code_has_explicit_country_elsewhere(leading.group(1), rest):
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
        word_leading = _LEADING_WORD_DASH_RE.match(cleaned)
        if (
            word_leading
            and word_leading.group(1).strip().lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS)
            and not _LEADING_ISO2_REGION_DASH_RE.match(cleaned)
        ):
            city_segment = word_leading.group(2).strip()
            rest = cleaned[word_leading.end():]
            word_code = word_leading.group(1).strip()
            if _leading_collision_code_has_explicit_country_elsewhere(word_code, rest):
                cleaned = f"{city_segment}{rest}"
            else:
                cleaned = f"{city_segment}, {word_code}{rest}"

    if "," not in cleaned:
        match = _TRAILING_SPACE_STATE_RE.search(cleaned)
        if match and match.group(1).lower() in (US_STATE_TOKENS | CA_PROVINCE_TOKENS):
            cleaned = cleaned[: match.start()] + ", " + match.group(1)
        else:
            remote_suffix = _LEADING_WORD_REMOTE_SUFFIX_RE.match(cleaned)
            if remote_suffix and remote_suffix.group(1).strip().lower() in (
                US_STATE_TOKENS | CA_PROVINCE_TOKENS
            ):
                state_segment = remote_suffix.group(1).strip()
                rest = cleaned[remote_suffix.start(2):]
                cleaned = f"{state_segment}, {rest}"
    return cleaned.strip() or raw


@dataclass(frozen=True)
class ParsedLocation:
    raw: str
    normalized_key: str
    city: str | None
    region: str | None
    country_code: str | None
    is_remote: bool


def _normalize_key(raw: str) -> str:
    """Trim + casefold + collapse whitespace — the only transformation ever
    used to decide "is this the same locations row as an existing one."
    Deliberately does NOT expand abbreviations or reorder tokens: that's
    exactly the kind of guess that could silently merge two different real
    places, which get_or_create_locations must never do at the identity
    level (see its docstring in db.py). Abbreviation/alias folding only
    happens for the separately-stored country_code/city/region fields below.
    """
    return _WHITESPACE_RE.sub(" ", raw.strip()).casefold()


@functools.lru_cache(maxsize=16384)
def parse_location(raw: str) -> ParsedLocation:
    """Best-effort structural parse of a raw scraped location string. Only
    `normalized_key` feeds row identity (see get_or_create_locations);
    city/region/country_code/is_remote are additive metadata for filtering,
    not used to decide whether two rows represent the same place.
    """
    # normalized_key (row identity — see get_or_create_locations) is always
    # derived from the untouched raw string, never the cleaned one: cleaning
    # is a best-effort aid to country/city/region/is_remote extraction only,
    # and must never change which `locations` row a given raw string maps
    # to, or two differently-formatted scrapes of the same posting could
    # silently dedup into two rows (or vice versa) depending on which one
    # a future cleaning-pattern tweak happens to match.
    normalized_key = _normalize_key(raw)
    cleaned = _clean_location_for_parsing(raw)
    # Checked against raw, not cleaned: cleanup steps exist to strip noise
    # for city/region/country extraction, and at least one of them (the
    # trailing "<ST> - <suffix>" strip) can legitimately discard a
    # trailing remote-keyword suffix ("Atlanta, GA - Remote") as part of
    # normal operation. raw can only ever contain MORE signal than
    # cleaned, never less, so this is strictly safer than checking
    # cleaned — no existing cleanup step removes a "remote" mention that
    # wasn't itself noise.
    is_remote = bool(_REMOTE_KEYWORD_RE.search(raw))
    country_code = resolve_country_from_location(cleaned)

    without_parens = _PAREN_RE.sub(" ", cleaned).strip()
    tokens = [t.strip() for t in without_parens.split(",") if t.strip()]

    city: str | None = None
    region: str | None = None
    if tokens:
        first = tokens[0]
        first_lower = first.lower()
        is_recognized_non_city = (
            first_lower in US_STATE_TOKENS
            or first_lower in CA_PROVINCE_TOKENS
            or first_lower in LOCATION_ALIASES
            or first_lower in _ISO_NAME_TO_CODE
            or first_lower in _BARE_ALPHA2_CODE_TO_COUNTRY
            or first_lower in _ALPHA3_US_CA_TOKENS
            or first_lower == "remote"
        )
        # A handful of real city names are also full US-state/CA-province
        # names ("New York", "Washington") — the checks above alone would
        # always read these as "not a city." When a *different* token
        # elsewhere in the string is itself a distinct, valid state/province
        # token, that's independent confirmation the first token is being
        # used as a place name rather than as the jurisdiction itself (a
        # region can't sensibly equal itself twice in one location string),
        # so the first-token-as-city reading wins instead. This only fires
        # for the specific name-collision case — it does not affect any
        # other US_STATE_TOKENS/CA_PROVINCE_TOKENS first-token match, e.g.
        # "California, USA" still correctly yields city=None.
        if is_recognized_non_city and (
            first_lower in US_STATE_TOKENS or first_lower in CA_PROVINCE_TOKENS
        ):
            other_tokens_lower = {t.strip().lower() for t in tokens[1:]}
            has_distinct_state_or_province_token = any(
                (t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS) and t != first_lower
                for t in other_tokens_lower
            )
            if has_distinct_state_or_province_token:
                is_recognized_non_city = False
        # Same collision, different table: a handful of real US city names
        # are also full country names ("Lebanon, TN", "Jordan, MN",
        # "Mexico, ME", "Chile, WI", "Panama, NY" — resolve_country_from_
        # location prioritizes the state/province reading for these, same
        # pre-existing trade-off noted below for the US/CA 2-letter-code
        # collisions). A trailing US-state/CA-province token elsewhere in
        # the string is the same independent confirmation as the guard
        # above — a country can't sensibly be its own trailing
        # jurisdiction — so it wins here too, just against
        # _ISO_NAME_TO_CODE/LOCATION_ALIASES instead of US_STATE_TOKENS/
        # CA_PROVINCE_TOKENS. Deliberately not merged into the guard above:
        # keeping the trigger conditions (which table first_lower hit)
        # separate keeps each easy to reason about on its own.
        #
        # Gated to _LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY, NOT the
        # full LOCATION_ALIASES table — confirmed live: "USA, VA, McLean"
        # was misfiring this guard (reading "USA" as a possible city
        # just because "VA" followed it), since "usa"/"us"/"uk"/"korea"/
        # etc. are never real place names anywhere, only "England"/
        # "Scotland"/"Wales"/"Holland"/"New York City" among
        # LOCATION_ALIASES' keys are genuinely also real US/CA town
        # names (verified against the gazetteer — see that set's own
        # comment).
        if is_recognized_non_city and (
            first_lower in _ISO_NAME_TO_CODE
            or first_lower in _LOCATION_ALIASES_AMBIGUOUS_WITH_US_CA_CITY
        ):
            other_tokens_lower = {t.strip().lower() for t in tokens[1:]}
            has_state_or_province_token = any(
                t in US_STATE_TOKENS or t in CA_PROVINCE_TOKENS for t in other_tokens_lower
            )
            if has_state_or_province_token:
                is_recognized_non_city = False
        # "<ST>, <City>, ..." — the reverse of the far more common "<City>,
        # <ST>" order ("TX, Austin, 11501 Alterra Pkwy STE 500", "NC,
        # Raleigh, 701 Corporate Center Dr STE 200", "NJ, Morris Plains,
        # 115 Tabor Rd"). is_recognized_non_city already correctly leaves
        # city=None here (tokens[0] is a real state token), but nothing
        # upstream ever looks at tokens[1] as the city this shape actually
        # has. Scoped narrowly to tokens[0] being a genuine, uncollided
        # US-state/CA-province token (is_recognized_non_city still True
        # after both collision guards above — a collided token means
        # tokens[0] IS the city, handled by the unconditional "if not
        # is_recognized_non_city" below, not this branch), and only when
        # tokens[1] itself isn't ALSO a recognized non-city token (a real
        # "<ST>, <ST2>, ..." or "<ST>, <Country>, ..." string has no city
        # here to extract, and must not have one guessed).
        if (
            is_recognized_non_city
            and (first_lower in US_STATE_TOKENS or first_lower in CA_PROVINCE_TOKENS)
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in _ISO_NAME_TO_CODE
                or second_lower in _NON_CITY_PHRASES
                or second_lower == "remote"
                or second_lower == "united states"
            )
            # region is set regardless of whether tokens[1] turns out to
            # be a real city or a known non-city phrase ("Utah, Work at
            # Home" still means Utah even though "Work at Home" isn't a
            # city) — confirmed live: this used to be bundled into the
            # same `if not second_is_non_city` guard as `city`, so a
            # string like "Utah Work at Home" (after
            # _LEADING_WORD_REMOTE_SUFFIX_RE's comma insertion) correctly
            # left city=None but ALSO wrongly left region=None, even
            # though tokens[0]="utah" is an unambiguous, confirmed state
            # token independent of what tokens[1] contains.
            region = first
            if not second_is_non_city:
                city = second

        # Same reversed shape, bare-alpha2-country-code-first instead of
        # state/province-first ("GB,Manchester", "AM,Yerevan",
        # "CN,Shenzhen"). No region assignment here — unlike the
        # state/province case above, tokens[0] is a whole country, not a
        # sub-national region, so `region` (which elsewhere in this
        # function only ever holds a state/province) stays unset;
        # country_code already carries this signal separately.
        if (
            city is None
            and is_recognized_non_city
            and first_lower in _BARE_ALPHA2_CODE_TO_COUNTRY
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in _ISO_NAME_TO_CODE
                or second_lower in _BARE_ALPHA2_CODE_TO_COUNTRY
                or second_lower in _NON_CITY_PHRASES
                or second_lower == "remote"
            )
            if not second_is_non_city:
                city = second

        # Same reversed shape again, full country NAME first instead of a
        # bare alpha-2 code ("Ireland, Limerick", "India, Bangalore",
        # "Philippines, Manila", "Netherlands, Amsterdam", "China,
        # Shanghai", "Canada, Vancouver", "Italy, Milan") — 284 rows
        # sampled from live pool data where country_code already resolved
        # correctly (via _ISO_NAME_TO_CODE) but city stayed None, since
        # nothing extracted tokens[1] as the city this shape actually has.
        # No region assignment, same reasoning as the bare-alpha2 branch
        # above — tokens[0] is a whole country, not a sub-national region.
        if (
            city is None
            and is_recognized_non_city
            and first_lower in _ISO_NAME_TO_CODE
            and len(tokens) >= 2
        ):
            second = tokens[1].strip()
            second_lower = second.lower()
            second_is_non_city = (
                second_lower in US_STATE_TOKENS
                or second_lower in CA_PROVINCE_TOKENS
                or second_lower in LOCATION_ALIASES
                or second_lower in _ISO_NAME_TO_CODE
                or second_lower in _BARE_ALPHA2_CODE_TO_COUNTRY
                or second_lower in _NON_CITY_PHRASES
                or second_lower == "remote"
            )
            if not second_is_non_city:
                city = second

        # "<CountryAlias>, <ST>, <City>" — 3-token, country-alias-first
        # instead of state/province-first ("USA, VA, McLean", "US, CO,
        # Longmont", "CAN, ON, London", "US, New Mexico, Albuquerque").
        # tokens[0] resolving via LOCATION_ALIASES/_ALPHA3_US_CA_TOKENS to
        # US/CA (not a bare state/province token, which the branch above
        # already covers, and not a bare ISO2 code, which the branch
        # above THAT covers) means tokens[1] is the real region and
        # tokens[2] the real city — currently nothing extracts either, so
        # city fell back to the opaque "USA"/"US"/"CAN" alias token
        # itself once city ends up staying None through every branch
        # above. Scoped to exactly 3 tokens: a 2-token "USA, VA" has no
        # city to extract (handled correctly by the unconditional "if
        # not is_recognized_non_city" fallback leaving city=None), and
        # >3 tokens risk the 3rd token being an address fragment rather
        # than the city — safer to decline than guess there.
        first_maps_to_us_or_ca = LOCATION_ALIASES.get(first_lower) in (
            "US",
            "CA",
        ) or _ALPHA3_US_CA_TOKENS.get(first_lower) in ("US", "CA")
        if city is None and is_recognized_non_city and first_maps_to_us_or_ca and len(tokens) == 3:
            second = tokens[1].strip()
            second_lower = second.lower()
            third = tokens[2].strip()
            third_lower = third.lower()
            if (second_lower in US_STATE_TOKENS or second_lower in CA_PROVINCE_TOKENS) and (
                third_lower not in _NON_CITY_PHRASES
                and third_lower not in US_STATE_TOKENS
                and third_lower not in CA_PROVINCE_TOKENS
                and third_lower not in LOCATION_ALIASES
                and third_lower not in _ISO_NAME_TO_CODE
            ):
                city = third
                region = second

        if not is_recognized_non_city and city is None:
            city = first

    # Many US-state/CA-province 2-letter tokens are themselves valid ISO
    # country codes for a different country ("DE" Delaware/Germany, "IN"
    # Indiana/India, "CA" California/Canada — 26 US + 5 CA collisions in
    # total). resolve_country_from_location() already has to make a call on
    # this ambiguity (it prioritizes the state/province reading over the ISO
    # country reading — a deliberate, pre-existing trade-off, not something
    # this function should relitigate). Gating region extraction on
    # country_code actually having resolved to US/CA keeps region
    # consistent with whatever call country resolution already made: a
    # token this function would extract as `region` is never one that
    # country resolution itself treated as signaling a non-US/CA country.
    # It does NOT independently correct a case where country_code itself is
    # wrong (e.g. "Berlin, DE" still resolves country_code to "US", so
    # region="DE" is still set) — that's resolve_country_from_location's
    # trade-off to own, not a new problem region extraction introduces on
    # top of it. What this guard does prevent: region_country_matches being
    # False (country_code resolved to neither "US" nor "CA" — e.g. a fuller
    # signal elsewhere in the string won a higher-priority match) never gets
    # silently overridden by a lower-confidence trailing 2-letter token.
    region_country_matches = country_code in ("US", "CA")
    if region_country_matches:
        if len(tokens) == 2:
            # A bare "City, ST" shape ("Washington, DC", "Toronto, ON") —
            # the region is the trailing token itself, tokens[-1]. The >= 3
            # branch below instead looks at tokens[-2] for a "City, Region,
            # Country" shape, and reusing that same index here would
            # silently read the *city* token back as its own region for any
            # 2-token string (since tokens[-2] == tokens[0] when there are
            # only two elements) — this is exactly the shape that most needs
            # region populated, since it's often the only disambiguating
            # signal available for an otherwise ambiguous city name (e.g.
            # three US towns are named "Washington"; without "DC" from this
            # branch, town_resolver.py can't tell them apart and must
            # refuse to guess).
            last = tokens[-1].strip()
            last_lower = last.lower()
            if last_lower in US_STATE_TOKENS or last_lower in CA_PROVINCE_TOKENS:
                region = last
        elif len(tokens) >= 3:
            second_to_last = tokens[-2].strip()
            second_to_last_lower = second_to_last.lower()
            if (
                second_to_last_lower in US_STATE_TOKENS
                or second_to_last_lower in CA_PROVINCE_TOKENS
            ):
                region = second_to_last

    # Correct the specific collision _CITY_REGION_COLLISION_TO_COUNTRY was
    # derived for: city/region resolved to a real-looking US-state/CA-
    # province pair ("Bangalore, IN"), but that region code is ALSO a
    # different country's ISO code, and this exact (city, code) pair has
    # no matching US/CA town while having exactly one match in the
    # collided-with country (see that table's own comment for the full
    # derivation method). Only ever narrows a US/CA reading to a more
    # specific real country — never touches country_code when it already
    # resolved to anything else, and never invents a city/region that
    # wasn't already there. region is cleared (not left as the stale
    # "IN") since region elsewhere in this file only ever means a real
    # US-state/CA-province code, and "IN" no longer means that once
    # country_code becomes India.
    if country_code in ("US", "CA") and city is not None:
        # NFD-fold accents before the lookup ("münchen" -> "munchen") —
        # the table's keys are derived from GeoNames' ascii_name, which
        # is already unaccented, so an accented city string would
        # otherwise silently miss a real entry (confirmed live:
        # "München, DE" stayed unmatched even though "munich"/"muenchen"
        # both resolve correctly). Same fold_accents approach as
        # resolve_country_from_location's own NFD pass above and
        # town_resolver.py's _fold_accents — safe here for the same
        # reason noted there: this only extracts a lookup key, it can
        # never merge two genuinely different places.
        city_folded = "".join(
            ch
            for ch in unicodedata.normalize("NFD", city)
            if unicodedata.category(ch) != "Mn"
        )
        city_keys = (city_folded.casefold(), city.casefold())
        # Try `region` first when it was extracted (the common case), but
        # also scan every raw token — confirmed live: "Lima, LIM, PE,
        # 15008" never populated `region` at all (tokens[-2]="LIM" isn't
        # a recognized state/province token, so the region-extraction
        # tiers above legitimately left it None), yet "pe" is still
        # sitting right there in tokens as the real collision code this
        # table exists to catch. Scanning tokens directly is strictly a
        # superset of the region-only check, so this replaces rather than
        # supplements it.
        candidate_codes = ([region.casefold()] if region else []) + [
            t.lower() for t in tokens if t.lower() != city.lower()
        ]
        corrected_country = None
        for code in candidate_codes:
            for city_key in city_keys:
                corrected_country = _CITY_REGION_COLLISION_TO_COUNTRY.get((city_key, code))
                if corrected_country is not None:
                    break
            if corrected_country is not None:
                break
        if corrected_country is not None:
            country_code = corrected_country
            region = None

    return ParsedLocation(
        raw=raw,
        normalized_key=normalized_key,
        city=city,
        region=region,
        country_code=country_code,
        is_remote=is_remote,
    )
