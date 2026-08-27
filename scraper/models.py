"""Normalized job model shared by all board scrapers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class JobDict(TypedDict):
    id: str
    company: str
    title: str
    location: str
    url: str
    posted_on: str
    source: str
    first_seen: str
    locations: list[str]
    posted_days: int | None
    posted_date: str | None
    description: str
    role_summary: str
    company_blurb: str


@dataclass
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

    def to_dict(self) -> JobDict:
        return JobDict(
            id=self.id,
            company=self.company,
            title=self.title,
            location=self.location,
            url=self.url,
            posted_on=self.posted_on,
            source=self.source,
            first_seen=self.first_seen,
            locations=self.locations,
            posted_days=self.posted_days,
            posted_date=self.posted_date,
            description=self.description,
            role_summary=self.role_summary,
            company_blurb=self.company_blurb,
        )

    @classmethod
    def from_dict(cls, data: JobDict) -> Job:
        return cls(
            id=data["id"],
            company=data["company"],
            title=data["title"],
            location=data["location"],
            url=data["url"],
            posted_on=data["posted_on"],
            source=data["source"],
            first_seen=data.get("first_seen", ""),
            locations=data.get("locations", []),
            posted_days=data.get("posted_days"),
            posted_date=data.get("posted_date"),
            description=data.get("description", ""),
            role_summary=data.get("role_summary", ""),
            company_blurb=data.get("company_blurb", ""),
        )
