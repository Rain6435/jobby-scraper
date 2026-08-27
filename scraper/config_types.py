"""TypedDicts for config.json's "companies" entries — one per board.

Every entry always has "name"/"board" (CompanyConfig, read by BaseScraper
itself) plus whatever fields that board's scraper needs from self.company.
Board-specific fields are named identically across several boards (most read
a plain "company" string) but kept as distinct types per board rather than
collapsed into one shared shape, so a config entry for the wrong board can't
silently type-check against a scraper that expects different semantics for
that field (a bamboohr subdomain is not a lever slug).
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class CompanyConfig(TypedDict):
    name: str
    board: str
    blurb: NotRequired[str]


class WorkdayConfig(CompanyConfig):
    url: str
    careers_base: NotRequired[str]


class GreenhouseConfig(CompanyConfig):
    token: str


class RipplingConfig(CompanyConfig):
    board_id: str


class AshbyConfig(CompanyConfig):
    slug: str


class BambooHrConfig(CompanyConfig):
    company: str


class BreezyConfig(CompanyConfig):
    company: str


class LeverConfig(CompanyConfig):
    company: str


class PersonioConfig(CompanyConfig):
    company: str


class RecruiteeConfig(CompanyConfig):
    company: str


class SmartRecruitersConfig(CompanyConfig):
    company: str


class TeamtailorConfig(CompanyConfig):
    company: str


class WorkableConfig(CompanyConfig):
    company: str


class ClimatebaseConfig(CompanyConfig):
    keywords: NotRequired[list[str]]


class UsajobsConfig(CompanyConfig):
    pass


class CmaHeritageConfig(CompanyConfig):
    pass


class CipPlanningConfig(CompanyConfig):
    pass


class IdcCareerCentreConfig(CompanyConfig):
    pass


class ConfigFile(TypedDict):
    companies: list[CompanyConfig]
