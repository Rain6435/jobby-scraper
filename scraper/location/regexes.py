"""Compiled regex patterns used by scraper/location/cleaning.py and
scraper/location/resolve.py to normalize free-text location strings before
tokenizing/matching. Kept in one module, in the original file's order,
rather than split further by which function consumes each one — an
earlier attempt to sort patterns by inferred caller (via a crude
substring-containment check) produced unreliable results, since comment
text mentioning a pattern's name made nearly every pattern look used by
multiple functions. Keeping them together in original order avoids
trusting that heuristic.
"""

from __future__ import annotations

import re

from scraper.location.data import COUNTRY_NAMES, LOCATION_ALIASES

PAREN_RE = re.compile(r"\(([^)]*)\)")

TRAILING_STATE_RE = re.compile(r"[,-]\s*([a-z]{2})\.?\s*$")

# Trailing "<City>, <ISO3>" shape ("Bengaluru, IND", "London, GBR",
# "Tokyo, JPN") — the existing comma-tokenizer below only checks each token
# against alias/name tables, and a bare 3-letter code matches neither.
TRAILING_ALPHA3_RE = re.compile(r"[,/-]\s*([a-z]{3})\.?\s*$")

# Some ATS vendors (confirmed on AtkinsRéalis's SmartRecruiters feed) format
# location as a dot-delimited "<ISO2>.<City>.<Address>" path instead of the
# comma-separated shape every other pass in this file assumes — e.g.
# "GB.Glasgow.2 Atlantic Square York Street" or "CA.QC.Montréal.455 boul.".
# Other vendors use the same idea with "-" instead of "." and/or an alpha-3
# code instead of alpha-2 ("CAN-ON-Kitchener", "JPN-Tokyo-OVOL",
# "BRA - Sao Paulo - Sao Paulo (Torre Z)" — the last with spaces around each
# dash). Splitting on ","/"-" (the tokenizer below, and TRAILING_STATE_RE)
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
LEADING_ISO2_DOT_RE = re.compile(r"^([a-z]{2})\.(?=\S)")

LEADING_ISO3_RE = re.compile(r"^([a-z]{3})\s*[,-]\s*(?=\S)")

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
LEADING_ISO2_REGION_DASH_RE = re.compile(r"^([A-Z]{2})-[A-Z0-9]{2,3}-")

LOCATION_ALIASES_COMBINED_RE = re.compile(
    r"(?:^|[^a-z])(?:"
    + "|".join(re.escape(alias) for alias in LOCATION_ALIASES)
    + r")(?:[^a-z]|$)",
    re.IGNORECASE,
)

COUNTRY_NAMES_COMBINED_RE = re.compile(
    r"(?:^|[^a-z])(?:"
    + "|".join(re.escape(name.lower()) for name in COUNTRY_NAMES.values())
    + r")(?:[^a-z]|$)",
    re.IGNORECASE,
)

# Trailing ", More..." noise suffix ("Michigan Remote Work, More...", "Ontario Remote Work, More...").
TRAILING_MORE_RE = re.compile(r",?\s*More\.{3}\s*$", re.IGNORECASE)

# Leading remote prefix with dash or slash or space ("Work at Home - Nevada", "Remote/Home Indiana", "Remote - Toronto").
LEADING_REMOTE_DASH_RE = re.compile(
    r"^\s*(?:work\s+(?:at|from)\s+home|remote/home|home/remote|remote|virtual|telework|home\s*office)\s*[-–—/ ]\s*(.+)$",
    re.IGNORECASE,
)

# Leading "Four Seasons " vendor prefix ("Four Seasons Dalian", "Four Seasons Hampshire", "Four Seasons Resort Napa Valley").
FOUR_SEASONS_PREFIX_RE = re.compile(
    r"^Four Seasons\s+(?:Resort\s+|Hotel\s+|Residence\s+Club\s+|Corporate\s+Office,\s*)?",
    re.IGNORECASE,
)

# Trailing Ngr store ID suffix ("Tampa 1286 Ngr", "Atlanta 2444 Ngr").
NGR_STORE_RE = re.compile(r"\s*\d{3,5}\s+Ngr\b", re.IGNORECASE)

# Trailing Metro Area / Area suffix ("Austin Metro Area", "Santiago De Querétaro_Area", "Montreal Area").
METRO_AREA_RE = re.compile(r"(?:\s+Metro)?(?:\s+Area|_Area)\s*$", re.IGNORECASE)

# Trailing street address after a comma ("Ajax, 59 Westney Rd S", "Mississauga, 2 Prologis Blvd").
TRAILING_CITY_ADDRESS_RE = re.compile(
    r",\s*\d+\b[\w\s.\x27-]*?\b(?:street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|lane|ln|way|court|ct|place|pl|pkwy|parkway)\b(?:\s+(?:north|south|east|west|n|s|e|w|ne|nw|se|sw)\b\.?)?(?=[,]|(?:\s*\(\d+\))?$)",
    re.IGNORECASE,
)

# Trailing Hub suffix ("Toronto, ON Hub", "Vancouver, BC Hub").
HUB_SUFFIX_RE = re.compile(r",\s*([A-Za-z]{2})\s+Hub\s*$", re.IGNORECASE)

# Leading "UNIQLO <ST>" retail store format ("UNIQLO MA Burlington Mall(UQUS)", "UNIQLO WA Tacoma mall(UQUS)").
UNIQLO_PREFIX_RE = re.compile(r"^UNIQLO\s+([A-Z]{2})\s+(.*?)(?:\s*\(UQUS\))?$", re.IGNORECASE)

# Desjardins Canadian financial cooperative ("Caisse Desjardins du Centre de Lotbinière", "Complexe Desjardins Montréal").
DESJARDINS_RE = re.compile(r"^(?:Caisse\s+(?:populaire\s+)?Desjardins|Complexe\s+Desjardins)\b", re.IGNORECASE)

# Venue prefix in 3-token strings ("Carrefour de l'Estrie, Sherbrooke, QC", "Head Office, Quebec City, QC", "42 East Baltimore Pike, Media, Pennsylvania").
VENUE_PREFIX_RE = re.compile(
    r"^\d+|\b(?:mall|carrefour|centre|center|office|building|naval\s+base|campus|station|tower)\b",
    re.IGNORECASE,
)

# Defunct-position prefix emitted by some ATS vendors ("DNU-ID-JW-JAKARTA...",
# "DNU-MX-NLE-MONTERREY...") — the "DNU" (Do Not Use) tag marks positions that
# were cancelled/archived. Stripping it exposes the standard ISO3-State-City
# vendor shape that LEADING_ISO3_RE / LEADING_ISO2_REGION_DASH_RE already
# handles. Pattern: optional whitespace around the dash, as the prefix is
# sometimes written "DNU - " with spaces and sometimes "DNU-" tight.
DNU_PREFIX_RE = re.compile(r"^DNU\s*[-\u2013]\s*", re.IGNORECASE)

# Broader than a bare "remote" match: catches the "Work at Home - Nevada" /
# "Virtual, DNK" / "US Remote - DC" shapes a real ATS emits for fully-remote
# postings that never actually say the word "remote" — sampled from live
# pool data where these were parsed but silently left is_remote=False.
REMOTE_KEYWORD_RE = re.compile(
    r"\b(remote|virtual|work[\s-]?from[\s-]?home|wfh|work\s+at\s+home)\b", re.IGNORECASE
)

WHITESPACE_RE = re.compile(r"\s+")

# Street-address prefix glued onto a city ("200 W Orangethorpe Ave,
# Fullerton,CA 92832-2900", "8680 Beechmont Ave, Cincinnati,OH 45255-4710").
# tokens[0] in parse_location would otherwise become the street address
# instead of the city. Matches a leading run that starts with a number and
# contains a common street-suffix word, up to (but not including) the next
# comma — deliberately narrow (suffix word required) so it never eats a
# legitimate "123 Main" style city/town name that has no street suffix.
STREET_ADDRESS_PREFIX_RE = re.compile(
    # "fl" (bare, for "floor") deliberately excluded from this leading
    # alternation despite "floor" itself being included — confirmed live:
    # "fl" collides with the 2-letter Florida state abbreviation ("FL -
    # St Petersburg" was misread as a "floor ... street" address prefix
    # and stripped down to "Petersburg", losing "St"), a collision risk
    # "floor" spelled out in full doesn't have.
    r"^(?:(?:\d+|suite|ste|level|floor|unit|bldg|building)\b[\w\s./\x27-]*?\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|"
    r"drive|dr|lane|ln|way|parkway|pkwy|highway|hwy|circle(?![\s-]k\b)|cir(?![\s-]k\b)|court|ct|"
    r"place|pl|square|sq|rue|boul|route|rte|chemin|ch)\b\.?"
    # Optional trailing compass-direction suffix ("7000 Target Pkwy N",
    # "15800 87th St NE") — common in US street addresses, sitting
    # between the street-suffix word and the next comma. Left
    # unconsumed, this became tokens[0] on its own once the rest of the
    # prefix was stripped ("N,NCD-0375 Brooklyn Park,MN"), leaking a
    # bare direction letter into `city`. Word-boundaried so it only
    # matches a standalone direction token, never eating into a real
    # word that happens to start the same way.
    r"(?:\s+(?:n|s|e|w|ne|nw|se|sw)\b\.?)?)(?:[,:;]\s*)?",
    re.IGNORECASE,
)

# French street-address prefix where the street word precedes the street name
# ("135-1, rue Principale, Sainte-Justine", "1000, rue De La Gauchetière Ouest, Montréal",
# "455 boul. René-Lévesque, Montréal", "123 chemin du Roy, Trois-Rivières",
# "159, boulevard Bégin  Sainte-Claire", "212 A, boulevard Labelle  Rosemère").
FRENCH_STREET_ADDRESS_PREFIX_RE = re.compile(
    r"^\d+[\w\s.'-]*(?:,\s*)?\b(?:boulevard|boul|route|rte|chemin|ch|rue|av|avenue)\b[^,]+(?:\s*[,:;]\s*|\s{2,})",
    re.IGNORECASE,
)

# Leading "Sysco " or "Freshpoint " vendor prefix ("Sysco Charlotte", "Freshpoint Nashville").
SYSCO_PREFIX_RE = re.compile(r"^(?:sysco|fresh[Pp]oint)\s+", re.IGNORECASE)

# Leading "Lowe's " vendor prefix ("Lowe's New Caney, TX BDC 3465", "Lowe's Shippensburg, PA BDC 3462").
LOWES_PREFIX_RE = re.compile(r"^Lowe['’]s\s+", re.IGNORECASE)

# Leading "SERVICES OFFICE, " or "ASKUITY OFFICE, " prefix ("SERVICES OFFICE, LAKELAND - 1435",
# "ASKUITY OFFICE, TORONTO - 2595").
SERVICES_OFFICE_PREFIX_RE = re.compile(
    r"^(?:services\s+office|askuity\s+office),\s*", re.IGNORECASE
)

# Facility/store-ID token glued onto a city with no separating comma
# ("Store 2743142 Murrysville PA", "Store0187 Lexington KY", "ST0189: Victoriaville",
# "27241 CIRCLE K GÄLLIVARE").
# Narrow to the literal "store" word plus digits, "ST" + digits, or digits + "Circle K",
# so it never strips a legitimately city-initial numeric token.
STORE_ID_PREFIX_RE = re.compile(
    r"^(?:store\s*#?\s*\d+|st\d+|\d+\s+circle\s+k)\s*[:\s-]?\s*", re.IGNORECASE
)

# Trailing facility suffix without dash ("TX BDC 3465", "PA BDC 3462", "TX BDC").
TRAILING_FACILITY_NO_DASH_RE = re.compile(
    r"\s+(?:bdc|rdc|fdc)(?:\s+\d{3,5})?\s*$", re.IGNORECASE
)

# Store ID + City + State + "Home Office" ("6361 Ossining NY Home Office", "3206 Stamford CT Home Office").
HOME_OFFICE_STORE_RE = re.compile(
    r"^\d{4,5}\s+([A-Za-z\s]+?)\s+([A-Za-z]{2}|Hawaii|Alaska)\s+Home\s+Office\s*$",
    re.IGNORECASE,
)

# Trailing office suffix after state ("Troy, MI Group Sales Office (035)", "Brownsville, WI Corporate Office").
OFFICE_SUFFIX_RE = re.compile(
    r",\s*([A-Za-z]{2})\s+(?:corporate|home|sales|group\s+sales|regional|branch)?\s*office(?:\s*\(\d+\))?\s*$",
    re.IGNORECASE,
)

# Trailing "STORE - NNNN", "RDC - NNNN", or "FDC/BDC - NNNN" suffix, city-first
# ("QUINCY STORE - 1915", "WESTFIELD RDC - 5221", "CHARLOTTE FDC/BDC - 5955",
# "Lowe's New Caney, TX BDC 3465").
TRAILING_STORE_SUFFIX_RE = re.compile(
    r"\s+(?:store|rdc|fdc(?:/bdc)?|bdc)?\s*-\s*\d+\s*$", re.IGNORECASE
)

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
LEADING_FACILITY_ID_DASH_RE = re.compile(r"^\d{5}\s*-\s*")

# Trailing US ZIP / ZIP+4, 6-digit international postal code (India's PIN code,
# Singapore's, Vietnam's, ...), Brazilian 5-digit-dash-3-digit, or 4-digit European code
# after comma ("Wayne, NJ, US, 07470", "Bangalore, Karnataka, IND, 560093",
# "Sao Paulo, São Paulo, BRA, 04578-133", "Klagenfurt, Carinthia, AUT, 9020",
# "Stockholm, SWE, 104 51").
TRAILING_ZIP_RE = re.compile(
    r"[,\s]+\d{5}(?:-\d{3,4})?\s*$|[,\s]+\d{6}\s*$|,\s*\d{4}\s*$|,\s*\d{3}\s+\d{2}\s*$"
)

# Trailing short (1-4 digit) facility/store code after the state token,
# space-separated rather than comma-separated ("Fayetteville, NC 0388",
# "Winchester, KY 0464", "League City, TX 2821", "Saratoga Springs, NY
# 0560") — same failure mode as the 5-digit ZIP case above (breaks the
# "...,<state>$" trailing-token match), just a shorter code. Requires a
# space (not comma) before the digits specifically so it never touches an
# already-correct "<City>, <ST>, <4-digit-something>" comma-separated
# shape — those have their own, already-working tokenization and this
# must not interfere with it. 5-digit is deliberately excluded here (that
# is TRAILING_ZIP_RE's job, run first) so the two never double-strip or
# disagree on where a boundary is.
TRAILING_SHORT_CODE_RE = re.compile(r"(?<=[A-Za-z])\s+\d{1,4}\s*$")

# Trailing "<ST> - <suffix>" after the LAST comma ("New Haven, CT - USA",
# "Dallas, TX - Data Center", "Charlotte, NC - Whitehall Park Dr",
# "USA, Virginia - Full Time Remote", "CAN, British Columbia - Full Time Remote") —
# the dash-glued suffix means tokens[-1] becomes "ct - usa" instead of the
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
TRAILING_STATE_DASH_SUFFIX_RE = re.compile(r",\s*([A-Za-z][A-Za-z ]*?)\s+-\s+[^,]+$")

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
TRAILING_DASH_STATE_PAREN_ZIP_RE = re.compile(
    r"^(.+)-([A-Za-z][A-Za-z ]*?)\(\d+\)\s*$"
)

# Trailing Canadian postal code ("London, ON, CA, N6E 1V4", "Montreal, QC,
# CA, H3B4G7") — letter-digit-letter [optional space] digit-letter-digit,
# the fixed Canada Post format. Same purpose as TRAILING_ZIP_RE: strip it
# so the string ends in the real jurisdiction token ("CA") instead, which
# is what the CA-province-collision tier in resolve_country_from_location
# needs to see. Anchored to the end only, same reasoning as the US ZIP
# pattern above.
TRAILING_CA_POSTAL_CODE_RE = re.compile(
    r"[,\s]+[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d\s*$"
)

# Trailing facility code stuck onto the end of a parenthetical, after the
# closing paren ("W. Jefferson, NC (W Jefferson) 2255", "Warwick, RI (N
# Warwick) 2397", "Chandler, AZ (W Chandler) 0674"). PAREN_RE strips the
# parenthetical's *contents* but not this trailing digit run — left in
# place, "NC (W Jefferson) 2255" collapses to tokens[-1] == "nc   2255"
# once the parens are gone, which fails the exact "last_lower in
# US_STATE_TOKENS" membership check even though the real state token (NC)
# is sitting right there. Digits only (no letters), so this never eats a
# trailing word.
TRAILING_PAREN_CODE_RE = re.compile(r"\)\s*\d+\s*$")

# Trailing parenthetical containing an explicit (City, Region/Country)
# ("HOKA Newbury Street Retail Store (Boston, MA)", "UGG Leesburg Premium Outlets (Leesburg, VA)",
# "HOKA Toronto Eaton Centre (Toronto, ON)", "HOKA Garibaldi Store (Milan, IT)").
# When the second token inside parens is a recognized US state, CA province,
# country alias, or country name, the parenthetical holds the real location.
TRAILING_PAREN_CITY_REGION_RE = re.compile(
    r"^(.+?)\s*\(([A-Za-z\s.'-]+),\s*([A-Za-z]{2,})\)\s*$"
)

# Colon-delimited street address / building / mall prefix before the city
# ("885 GEORGIA ST W:VANCOUVER", "ROYAL BANK PLAZA, 200 BAY ST:TORONTO",
# "345 RUE DES SAGUENÉENS, FLOOR 2:SAGUENAY").
COLON_STREET_CITY_RE = re.compile(
    r"^(?:.*\b(?:\d+|street|st|avenue|ave|road|rd|boulevard|blvd|boul|rue|rte|drive|dr|lane|ln|way|parkway|pkwy|highway|hwy|circle|cir|court|ct|place|pl|square|sq|plaza|tower|centre|center|floor|branch|house)\b.*?):\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.'-]+)$",
    re.IGNORECASE,
)

# Trailing street address suffix after a city ("Saskatoon-1816 McOrmond Dr",
# "Edmonton - 103 St", "Austin-5900 E Ben White Blvd (10703)",
# "Houston - 1311 W. Sam Houston Pkwy N., Ste. 150 (10400)").
TRAILING_ADDRESS_RE = re.compile(
    r"\s*-\s*\d+[\w\s.,\x27-]*?\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|parkway|pkwy|highway|hwy|circle|cir|court|ct|place|pl|square|sq|rue|boul|route|rte|chemin)\b(?:\s+(?:north|south|east|west|n|s|e|w|ne|nw|se|sw)\b\.?)?(?:\s*,\s*(?:ste|suite|unit|apt|bldg|building|fl|floor)\b[\w\s.-]*)?(?:\s*\(\d+\))?\s*$",
    re.IGNORECASE,
)

# Trailing UK postal code ("5 Southampton Street, London WC2E 7HA", "Reading, GBR, RG6 1PT").
TRAILING_UK_POSTAL_CODE_RE = re.compile(
    r"[,\s]+([A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2})\s*$",
    re.IGNORECASE,
)

# "<City> <ST> - <Facility>" ("Bloomington MN - Country Inn Bloomington",
# "Denver PA - 465 Swamp Bridge Road", "Hagerstown MD-Op Ctr").
CITY_ST_FACILITY_RE = re.compile(
    r"^([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27]+?)\s+([A-Z]{2})\s*-\s*([A-Za-z0-9].*)$"
)

# Leading "<Country>-<State>-<City>" ("US-CA-EL SEGUNDO-R01", "CA-AB-CALGARY-6820 36 STREET SE",
# "US-CA - San Diego").
COUNTRY_ST_DASH_RE = re.compile(
    r"^(US|USA|CA|CAN)-([A-Za-z]{2})\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)(?:\s*[-–~]\s*(.*))?$",
    re.IGNORECASE,
)

# Leading "<Country>-<FullStateName>-<City>" ("US-Ohio-Tallmadge-184 South Avenue").
COUNTRY_STATE_WORD_DASH_RE = re.compile(
    r"^(US|USA|CA|CAN)-([A-Za-z]+)-([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)(?:\s*[-–~]\s*(.*))?$",
    re.IGNORECASE,
)

# Leading "<Country> - <State/City> - <City/State>" ("US - Florida - Pensacola", "USA - Florida - Miami",
# "CA - British Columbia - Vancouver", "US - Richmond - VA", "US - Betts - SD").
COUNTRY_DASH_3PART_RE = re.compile(
    r"^(US|USA|CA|CAN)\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)(?:\s*[-–~]\s*(.*))?$",
    re.IGNORECASE,
)

# International "<ISO3> - <Region> - <City>" ("GBR - England - Reading", "DEU - Hesse - Biebesheim",
# "MEX - Jalisco - Guadalajara", "CHN - Sichuan - Chengdu").
ISO3_REGION_CITY_RE = re.compile(
    r"^([A-Z]{3})\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)(?:\s*[-–~]\s*(.*))?$"
)

# Leading "<ISO3> - <City>" ("CZE - Brno", "BRA-Barueri", "CHL-Santiago-Technology-Center").
ISO3_DASH_CITY_RE = re.compile(
    r"^([A-Z]{3})\s*[-–]\s*([A-Za-zÀ-ÖØ-öø-ÿ\s.\x27-]+?)(?:\s*[-–~]\s*(.*))?$"
)

# Trailing attendance / hybrid policy phrase ("Seattle 2+ days in office",
# "Herndon 2+ days in office").
TRAILING_ATTENDANCE_POLICY_RE = re.compile(
    r"\s+\d+\+?\s*days?\s+(?:in\s+office|on[\s-]site|remote|wfh|at\s+home)\b.*$",
    re.IGNORECASE,
)

# Space-joined "CAN <Province> <City>" ("CAN Quebec Québec", "CAN Alberta Edmonton").
CAN_SPACE_PROV_CITY_RE = re.compile(r"^CAN\s+([A-Za-z]+)\s+([A-Za-zÀ-ÖØ-öø-ÿ\s]+)$")

# "<City> - <CountryCode>" ("Guangzhou - CN", "Shanghai - CN", "Dublin - IE", "Manchester - GBR").
CITY_DASH_COUNTRY_CODE_RE = re.compile(
    r"^([A-Za-zÀ-ÖØ-öø-ÿ\s.'-]+?)\s*-\s*([A-Za-z]{2,3})$"
)

# "<City> - <State>" ("Jacksonville - Florida", "Salem - Ohio").
CITY_DASH_STATE_RE = re.compile(
    r"^([A-Za-zÀ-ÖØ-öø-ÿ\s.'-]+?)\s*-\s*([A-Za-z\s]+)$"
)

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
TRAILING_SPACE_STATE_RE = re.compile(r"(?<=[A-Za-z])\s+([A-Z]{2})\s*$")

# Leading "<ST> - <City>" / "<ST>-<City>" ("WV - Triadelphia, 215 Cabela Dr
# - Retail XFR2716", "CT-WALLINGFORD, 108 LEIGUS RD", "WA - Fife",
# "NC-Rocky Mount-PAM Specialty Hospital"). A documented, deliberately
# unhandled ambiguity in resolve_country_from_location itself (see
# LEADING_ISO2_REGION_DASH_RE's comment: it requires the whole
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
LEADING_SPACE_STATE_DASH_RE = re.compile(
    r"^([A-Z]{2})\s*-\s*([A-Za-z][^,-]*)"
)

# Leading full state/province name + dash ("Idaho - Boise", "Kansas -
# Great Bend") — same shape and purpose as LEADING_SPACE_STATE_DASH_RE,
# just a full name instead of a 2-letter code. No ALL-CAPS guard needed
# here (unlike the 2-letter case): a full state name has no same-shaped
# ISO-country-code collision risk to exclude, since resolve_country_from_
# location has no "<full word>-<City>" ATS vendor tier this could be
# confused with. Case-insensitive on the captured segment itself; the
# membership check against US_STATE_TOKENS/CA_PROVINCE_TOKENS (which are
# all-lowercase keys) happens in Python, not in this regex.
LEADING_WORD_DASH_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*-\s*([A-Za-z][^,-]*)")

# Leading full state/province name + trailing remote-phrase, space-joined
# with no dash or comma at all ("Utah Work at Home", "Oregon Virtual",
# "Tennessee Work at Home", "West Virginia Work at Home") — a real,
# fairly common ATS shape (60 rows sampled) distinct from the dash-joined
# "<ST> - Remote" case LEADING_SPACE_STATE_DASH_RE/LEADING_WORD_DASH_RE
# already handle. Anchored on the remote-phrase being the trailing,
# whole-string suffix (via REMOTE_KEYWORD_RE's own alternation, reused
# here rather than duplicated) so the leading segment captured in group 1
# is whatever comes before it; that segment is then validated against
# US_STATE_TOKENS/CA_PROVINCE_TOKENS in Python before any comma is
# inserted, same "regex finds the shape, a table membership check decides
# whether to trust it" split as every other cleanup pattern in this file.
LEADING_WORD_REMOTE_SUFFIX_RE = re.compile(
    r"^([A-Za-z][A-Za-z ]*?)\s+"
    r"(remote(?:\s+work)?|virtual(?:\s+work)?|work[\s-]?from[\s-]?home|wfh|work\s+at\s+home)\s*$",
    re.IGNORECASE,
)

# Leading regional-org prefix + dash-delimited "<Country> - <Region-or-
# City> - [<City-or-suffix>]" ("AMER - Canada - Alberta - Calgary - 8th
# Street NE", "AMER - United States - Georgia - Offsite/Home", "EMEA -
# Germany - Munich - Balanstrasse", "APAC - India - New Delhi") — a
# distinct ATS vendor convention grouping postings by sales region
# (AMER/EMEA/APAC/LATAM) ahead of the actual location, with no comma
# anywhere in the string, so the existing comma-based tokenizer never
# separates it at all (the whole string became one opaque, unresolvable
# token). Only strips the org-region prefix itself; the remaining
# "<Country> - <Region-or-City> - ..." is left dash-delimited for
# COUNTRY_DASH_3PART_RE and friends to continue
# handling exactly as they already do for an ordinary leading-country-dash
# shape.
LEADING_ORG_REGION_PREFIX_RE = re.compile(
    r"^(?:AMER|EMEA|APAC|LATAM)\s*-\s*(?=\S)", re.IGNORECASE
)
