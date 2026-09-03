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
# Generated from GeoNames' cities15000 dump (scraper/gazetteer.py's bundled
# data/gazetteer/cities15000.txt.gz — the same dataset scraper/
# town_resolver.py's DB-backed matching uses for a different purpose:
# resolving a specific town given an ALREADY-KNOWN country). Built by
# grouping every gazetteer row by lowercased ascii_name and keeping only
# names that map to EXACTLY ONE country_code across the full ~34k-row
# worldwide dataset — no population-based tie-breaking, which a spot check
# showed gets real cases wrong even for "obviously safe" names (e.g.
# "Richmond" resolves to a US town over Richmond, BC by a slim population
# margin; "Georgetown" resolves to Guyana over the common Ontario usage).
# Ties are excluded entirely rather than guessed, preserving this
# function's "never guess" contract. Further filtered to city names
# actually observed in scraped job locations, then hand-reviewed to drop
# two false positives that technically have a single-country gazetteer
# match but are unsafe to trust bare: "apac" (a real Ugandan town, but in
# job postings this string is virtually always the Asia-Pacific acronym)
# and "federal" (a real Argentine town, too generic/administrative a word
# to trust without other context).
#
# To add more entries later, re-run the same derivation against newly
# observed unresolved locations rather than hand-typing a new city —
# hand-typing skips the single-country-match safety check this table's
# entries all passed.
_BARE_CITY_NAME_TO_COUNTRY: dict[str, str] = {
    "abbotsford": "CA",
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
    "belgrade": "RS",
    "belo horizonte": "BR",
    "berlin": "DE",
    "bogota": "CO",
    "brampton": "CA",
    "bratislava": "SK",
    "bremen": "DE",
    "brownsville": "US",
    "bucharest": "RO",
    "budapest": "HU",
    "buenos aires": "AR",
    "caen": "FR",
    "calgary": "CA",
    "cape town": "ZA",
    "cardiff": "GB",
    "carlsbad": "US",
    "catania": "IT",
    "chengdu": "CN",
    "chennai": "IN",
    "chicago": "US",
    "chongqing": "CN",
    "coimbra": "PT",
    "copenhagen": "DK",
    "dallas": "US",
    "dothan": "US",
    "dubai": "AE",
    "edinburgh": "GB",
    "eindhoven": "NL",
    "espoo": "FI",
    "fond du lac": "US",
    "fort erie": "CA",
    "fuzhou": "CN",
    "getafe": "ES",
    "glasgow": "GB",
    "gondia": "IN",
    "greenwood": "US",
    "guangzhou": "CN",
    "gurugram": "IN",
    "hamburg": "DE",
    "hangzhou": "CN",
    "hebron": "PS",
    "houston": "US",
    "hsinchu": "TW",
    "indianapolis": "US",
    "islamabad": "PK",
    "ivrea": "IT",
    "jacksonville": "US",
    "jakarta": "ID",
    "jena": "DE",
    "jerusalem": "IL",
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
    "macclesfield": "GB",
    "makati city": "PH",
    "mannheim": "DE",
    "markham": "CA",
    "medellin": "CO",
    "miami": "US",
    "milan": "IT",
    "milwaukee": "US",
    "mississauga": "CA",
    "montpellier": "FR",
    "montreal": "CA",
    "monza": "IT",
    "morrisville": "US",
    "mumbai": "IN",
    "munich": "DE",
    "neenah": "US",
    "new delhi": "IN",
    "niagara-on-the-lake": "CA",
    "noida": "IN",
    "nottingham": "GB",
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
    "prague": "CZ",
    "pune": "IN",
    "puurs": "BE",
    "quezon city": "PH",
    "quito": "EC",
    "raleigh": "US",
    "red deer": "CA",
    "rennes": "FR",
    "riga": "LV",
    "riyadh": "SA",
    "saint-georges": "CA",
    "salmon arm": "CA",
    "san salvador": "SV",
    "santo amaro": "BR",
    "sao paulo": "BR",
    "sarnia": "CA",
    "saskatoon": "CA",
    "sault ste. marie": "CA",
    "seattle": "US",
    "seoul": "KR",
    "sepang": "MY",
    "shanghai": "CN",
    "sheffield": "GB",
    "shenzhen": "CN",
    "sibiu": "RO",
    "sidney": "US",
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
    "toronto": "CA",
    "toulouse": "FR",
    "tucson": "US",
    "turku": "FI",
    "ulm": "DE",
    "vaughan": "CA",
    "vilvoorde": "BE",
    "waltham": "US",
    "warsaw": "PL",
    "westlake": "US",
    "winnipeg": "CA",
    "yokohama": "JP",
}


def _matches_word(normalized: str, phrase: str) -> bool:
    escaped = re.escape(phrase)
    return re.search(rf"(?:^|[^a-z]){escaped}(?:[^a-z]|$)", normalized) is not None


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
        code = LOCATION_ALIASES.get(token)
        if code:
            return code
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
        return "US" if last_us_index > last_ca_index else "CA"

    for token in tokens:
        code = _ISO_NAME_TO_CODE.get(token)
        if code:
            return code

    for alias, code in LOCATION_ALIASES.items():
        if _matches_word(without_parens, alias):
            return code
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


_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


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


def parse_location(raw: str) -> ParsedLocation:
    """Best-effort structural parse of a raw scraped location string. Only
    `normalized_key` feeds row identity (see get_or_create_locations);
    city/region/country_code/is_remote are additive metadata for filtering,
    not used to decide whether two rows represent the same place.
    """
    normalized_key = _normalize_key(raw)
    is_remote = bool(_REMOTE_RE.search(raw))
    country_code = resolve_country_from_location(raw)

    without_parens = _PAREN_RE.sub(" ", raw).strip()
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
        if not is_recognized_non_city:
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

    return ParsedLocation(
        raw=raw,
        normalized_key=normalized_key,
        city=city,
        region=region,
        country_code=country_code,
        is_remote=is_remote,
    )
