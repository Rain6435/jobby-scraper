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


class PinpointConfig(CompanyConfig):
    company: str


class JobviteConfig(CompanyConfig):
    company_id: str


class JazzHrConfig(CompanyConfig):
    company: str


class GovernmentJobsConfig(CompanyConfig):
    agency: str


class ReliefwebConfig(CompanyConfig):
    pass


class OracleCloudConfig(CompanyConfig):
    tenant: str
    site_number: NotRequired[str]


class SuccessFactorsConfig(CompanyConfig):
    company: str
    domain: NotRequired[str]


class AdpConfig(CompanyConfig):
    cid: str
    cc_id: NotRequired[str]


class PaylocityConfig(CompanyConfig):
    guid: str


class IcimsConfig(CompanyConfig):
    tenant: str
    domain: NotRequired[str]


class IBMConfig(CompanyConfig):
    pass


class AmazonConfig(CompanyConfig):
    category: NotRequired[str]
    country: NotRequired[str]
    business_category: NotRequired[str]
    max_pages: NotRequired[int]


class MicrosoftConfig(CompanyConfig):
    location: NotRequired[str]
    query: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class AppleConfig(CompanyConfig):
    search: NotRequired[str]
    location: NotRequired[str]
    team: NotRequired[str]
    max_pages: NotRequired[int]


class ValveConfig(CompanyConfig):
    fetch_details: NotRequired[bool]


class TikTokConfig(CompanyConfig):
    keyword: NotRequired[str]
    max_pages: NotRequired[int]


class NetflixConfig(CompanyConfig):
    query: NotRequired[str]
    location: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class GoogleConfig(CompanyConfig):
    query: NotRequired[str]
    location: NotRequired[str]
    company_name: NotRequired[str]
    max_pages: NotRequired[int]


class EAConfig(CompanyConfig):
    search: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class AtlassianConfig(CompanyConfig):
    category: NotRequired[str]
    location: NotRequired[str]
    keyword: NotRequired[str]


class ShopifyConfig(CompanyConfig):
    location: NotRequired[str]
    keyword: NotRequired[str]
    fetch_details: NotRequired[bool]


class PhenomConfig(CompanyConfig):
    url: str
    location: NotRequired[str]
    category: NotRequired[str]
    keyword: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class JibeConfig(CompanyConfig):
    tenant: NotRequired[str]
    url: NotRequired[str]
    max_pages: NotRequired[int]


class MetaConfig(CompanyConfig):
    query: NotRequired[str]


class JaneStreetConfig(CompanyConfig):
    location: NotRequired[str]


class GCJobsConfig(CompanyConfig):
    title: NotRequired[str]
    department: NotRequired[str]
    location: NotRequired[str]
    language: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class QuebecEmploiConfig(CompanyConfig):
    title: NotRequired[str]
    query: NotRequired[str]
    location: NotRequired[str]
    region: NotRequired[str]
    regions: NotRequired[list[str]]
    language: NotRequired[str]
    max_pages: NotRequired[int]
    fetch_details: NotRequired[bool]


class ConfigFile(TypedDict):
    companies: list[CompanyConfig]
