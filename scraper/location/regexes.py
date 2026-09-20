"""Compiled regex patterns used by scraper/location/cleaning.py and
scraper/location/resolve.py to normalize free-text location strings before
tokenizing/matching. Kept in one module, in the original file's order.
"""

from __future__ import annotations

import re

from scraper.location.data import COUNTRY_NAMES, LOCATION_ALIASES


PAREN_RE = re.compile(r"\(([^)]*)\)")



TRAILING_STATE_RE = re.compile(r"[,-]\s*([a-z]{2})\.?\s*$")



# Trailing "<City>, <ISO3>" shape ("Bengaluru, IND", "London, GBR",
# "Tokyo, JPN") — the existing comma-tokenizer below only checks each token
# against alias/name tables, and a bare 3-letter code matches neither.
TRAILING_ALPHA3_RE = re.compile(r"[,/]\s*([a-z]{3})\.?\s*$")



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



LEADING_ISO3_DASH_RE = re.compile(r"^([a-z]{3})\s*-\s*(?=\S)")



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
STORE_ID_PREFIX_RE = re.compile(r"^store\s*#?\s*\d+\s+", re.IGNORECASE)



# Trailing "STORE - NNNN" suffix, city-first ("QUINCY STORE - 1915",
# "PICKERING STORE - 7238", "STATE BRIDGE RD STORE - 0131") — the mirror
# image of STORE_ID_PREFIX_RE's leading shape, from a different vendor
# convention. No state/country signal is present in this shape (unlike
# the leading-store-ID case, which usually has one after the store ID),
# so this only recovers `city` — still real progress for town_resolver.py,
# which can match on a bare city name via its own name-only tier. Anchored
# to the end with the literal " STORE - " + digits sequence, so it never
# strips a legitimate mid-string "store" mention.
TRAILING_STORE_SUFFIX_RE = re.compile(r"\s+store\s*-\s*\d+\s*$", re.IGNORECASE)



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



# Trailing US ZIP / ZIP+4, or a 6-digit international postal code
# (India's PIN code, Singapore's, Vietnam's, ...) after the state/
# country token has already been captured ("Wayne, NJ, US, 07470",
# "Bangalore, Karnataka, IND, 560093", "Singapore, SG, 797546") — left in
# place, this breaks TRAILING_STATE_RE's/TRAILING_ALPHA3_RE's
# "...,<code>$" anchor since the string no longer ends in the real
# jurisdiction token. Confirmed live: "Bangalore, Karnataka, IND, 560093"
# stayed country_code=None even though "IND" alone (no trailing digits)
# resolves correctly — the 6-digit PIN code broke the alpha-3 match the
# same way a 5-digit US ZIP breaks the 2-letter state match. Stripped
# from the end only, never mid string, so it can't accidentally eat a
# real 5/6-digit town/suite identifier elsewhere in the string.
TRAILING_ZIP_RE = re.compile(r"[,\s]+\d{5}(?:-\d{4})?\s*$|[,\s]+\d{6}\s*$")



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
TRAILING_STATE_DASH_SUFFIX_RE = re.compile(r",\s*([A-Za-z]{2})\s+-\s+[^,]+$")



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
    r"(remote|virtual|work[\s-]?from[\s-]?home|wfh|work\s+at\s+home)\s*$",
    re.IGNORECASE,
)


