"""Normalized job model shared by all board scrapers."""

from __future__ import annotations

from dataclasses import dataclass, field


# slots=True: no per-instance __dict__. A run holds one Job per posting for
# both the previous and current snapshot (tens of thousands each), so the
# dict overhead is paid twice per posting — see scripts/bench_memory.py.
@dataclass(slots=True)
class Job:
    id: str  # "{company_slug}:{stable_external_id}" — used as the diff key
    company: str
    title: str
    location: str  # primary location (first one)
    url: str  # direct link to the posting
    posted_on: str  # raw text from the board, e.g. "Posted 3 Days Ago"
    source: str  # board name, e.g. "workday"
    first_seen: str = ""  # ISO timestamp, set when first added to the snapshot
    locations: list[str] = field(default_factory=lambda: [])  # all locations, expanded
    posted_days: int | None = None  # days since posting, parsed from posted_on
    # Absolute posting date, "YYYY-MM-DD". Normally derived at write time from
    # first_seen minus posted_days, but carried here so a job reconstructed
    # from a previous run keeps the date it already had: posted_days comes
    # only from a live scrape, so recomputing it for a carried-over job
    # yields None and silently erases a date that was already correct.
    posted_date: str | None = None
    description: str = ""  # plain-text posting body, HTML stripped, truncated
    role_summary: str = ""  # 1-2 sentence AI summary of this specific posting
    company_blurb: str = ""  # short AI blurb about the company, from config.json
    company_logo: str = ""  # path to unified company SVG logo file, from config.json
    # Umbrella label for boards that map many distinct per-posting `company`
    # values (e.g. gc_jobs.py's per-department "RCMP"/"Health Canada"/etc.)
    # under one broader entity ("Government of Canada"). "" for every board
    # where `company` is already the right filterable identity on its own.
    company_group: str = ""
    # Denormalized from config.json's per-company "default_country" (see
    # main.py), same pattern as company_blurb above. Passed through to
    # parse_location() as a fallback ONLY when a job's location string
    # itself carries no country signal at all — never overrides a country
    # the string did resolve. Reserved for a confirmed single-country
    # employer (e.g. DaVita is US-only, Home Depot Canada is CA-only);
    # "" (the default) means no fallback, same as every other board.
    default_country: str = ""
