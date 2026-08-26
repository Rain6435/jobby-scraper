"""Normalized job model shared by all board scrapers."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field, fields


@dataclass
class Job:
    id: str          # "{company_slug}:{stable_external_id}" — used as the diff key
    company: str
    title: str
    location: str    # primary location (first one)
    url: str         # direct link to the posting
    posted_on: str   # raw text from the board, e.g. "Posted 3 Days Ago"
    source: str      # board name, e.g. "workday"
    first_seen: str = ""  # ISO timestamp, set when first added to the snapshot
    locations: list[str] = field(default_factory=list)  # all locations, expanded
    posted_days: int | None = None  # days since posting, parsed from posted_on
    # Absolute posting date, "YYYY-MM-DD". Normally derived at write time from
    # first_seen minus posted_days, but carried here so a job reconstructed
    # from a previous run keeps the date it already had: posted_days comes
    # only from a live scrape, so recomputing it for a carried-over job
    # yields None and silently erases a date that was already correct.
    posted_date: str | None = None
    description: str = ""      # plain-text posting body, HTML stripped, truncated
    role_summary: str = ""     # 1-2 sentence AI summary of this specific posting
    company_blurb: str = ""    # short AI blurb about the company, from config.json

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
