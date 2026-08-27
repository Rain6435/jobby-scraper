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
_TRAILING_STATE_RE = re.compile(r"[,-]\s*([a-z]{2})\s*$")


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

    normalized = location.lower()
    paren_tokens = [m.group(1).strip() for m in _PAREN_RE.finditer(normalized)]
    without_parens = _PAREN_RE.sub(" ", normalized)
    tokens = [t.strip() for t in re.split(r"[,/|]", without_parens) if t.strip()]
    tokens += [t for t in paren_tokens if t]

    for token in tokens:
        code = LOCATION_ALIASES.get(token)
        if code:
            return code
    for token in tokens:
        if token in US_STATE_TOKENS:
            return "US"
        if token in CA_PROVINCE_TOKENS:
            return "CA"

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
        if not is_recognized_non_city:
            city = first

    if len(tokens) >= 2:
        second_to_last = tokens[-2].strip()
        second_to_last_lower = second_to_last.lower()
        if second_to_last_lower in US_STATE_TOKENS or second_to_last_lower in CA_PROVINCE_TOKENS:
            region = second_to_last

    return ParsedLocation(
        raw=raw,
        normalized_key=normalized_key,
        city=city,
        region=region,
        country_code=country_code,
        is_remote=is_remote,
    )
