"""Scraper registry: maps the "board" field in config.json to a scraper class."""

from scraper.boards.ashby import AshbyScraper
from scraper.boards.bamboohr import BambooHRScraper
from scraper.boards.breezy import BreezyScraper
from scraper.boards.climatebase import ClimatebaseScraper
from scraper.boards.cma_heritage import CmaHeritageScraper
from scraper.boards.cip_planning import CipPlanningScraper
from scraper.boards.idc_career_centre import IdcCareerCentreScraper
from scraper.boards.greenhouse import GreenhouseScraper
from scraper.boards.lever import LeverScraper
from scraper.boards.personio import PersonioScraper
from scraper.boards.recruitee import RecruiteeScraper
from scraper.boards.rippling import RipplingScraper
from scraper.boards.smartrecruiters import SmartRecruitersScraper
from scraper.boards.teamtailor import TeamtailorScraper
from scraper.boards.usajobs import UsajobsScraper
from scraper.boards.workable import WorkableScraper
from scraper.boards.workday import WorkdayScraper

SCRAPERS = {
    WorkdayScraper.source: WorkdayScraper,
    GreenhouseScraper.source: GreenhouseScraper,
    RipplingScraper.source: RipplingScraper,
    BambooHRScraper.source: BambooHRScraper,
    AshbyScraper.source: AshbyScraper,
    BreezyScraper.source: BreezyScraper,
    ClimatebaseScraper.source: ClimatebaseScraper,
    CmaHeritageScraper.source: CmaHeritageScraper,
    IdcCareerCentreScraper.source: IdcCareerCentreScraper,
    CipPlanningScraper.source: CipPlanningScraper,
    LeverScraper.source: LeverScraper,
    SmartRecruitersScraper.source: SmartRecruitersScraper,
    PersonioScraper.source: PersonioScraper,
    RecruiteeScraper.source: RecruiteeScraper,
    UsajobsScraper.source: UsajobsScraper,
    WorkableScraper.source: WorkableScraper,
    TeamtailorScraper.source: TeamtailorScraper,
}
