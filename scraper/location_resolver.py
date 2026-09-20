"""Backward-compatible re-export — see scraper/location/ for the real
implementation (split into data.py/regexes.py/cleaning.py/resolve.py/
parse.py/export.py, 2026-09-19). Kept so `from scraper.location_resolver
import ...` continues to work unchanged for every existing caller.
"""

from __future__ import annotations

from scraper.location import (
    CA_PROVINCE_TOKENS,
    US_STATE_TOKENS,
    ParsedLocation,
    export_location_tables,
    parse_location,
    resolve_country_from_location,
)
from scraper.location.cleaning import clean_location_for_parsing  # used directly by tests

__all__ = [
    "CA_PROVINCE_TOKENS",
    "ParsedLocation",
    "US_STATE_TOKENS",
    "clean_location_for_parsing",
    "export_location_tables",
    "parse_location",
    "resolve_country_from_location",
]
