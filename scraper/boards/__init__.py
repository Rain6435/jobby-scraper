"""Scraper registry: maps the "board" field in config.json to a scraper class."""

from scraper.boards.adp import AdpScraper
from scraper.boards.amazon import AmazonScraper
from scraper.boards.apple import AppleScraper
from scraper.boards.ashby import AshbyScraper
from scraper.boards.atlassian import AtlassianScraper
from scraper.boards.bamboohr import BambooHRScraper
from scraper.boards.breezy import BreezyScraper
from scraper.boards.cip_planning import CipPlanningScraper
from scraper.boards.climatebase import ClimatebaseScraper
from scraper.boards.cma_heritage import CmaHeritageScraper
from scraper.boards.ea import EaScraper
from scraper.boards.google import GoogleScraper
from scraper.boards.governmentjobs import GovernmentJobsScraper
from scraper.boards.greenhouse import GreenhouseScraper
from scraper.boards.ibm import IBMScraper
from scraper.boards.icims import IcimsScraper
from scraper.boards.idc_career_centre import IdcCareerCentreScraper
from scraper.boards.janestreet import JaneStreetScraper
from scraper.boards.jazzhr import JazzHrScraper
from scraper.boards.jibe import JibeScraper
from scraper.boards.jobvite import JobviteScraper
from scraper.boards.lever import LeverScraper
from scraper.boards.meta import MetaScraper
from scraper.boards.microsoft import MicrosoftScraper
from scraper.boards.netflix import NetflixScraper
from scraper.boards.oraclecloud import OracleCloudScraper
from scraper.boards.paylocity import PaylocityScraper
from scraper.boards.personio import PersonioScraper
from scraper.boards.phenom import PhenomScraper
from scraper.boards.pinpoint import PinpointScraper
from scraper.boards.recruitee import RecruiteeScraper
from scraper.boards.reliefweb import ReliefwebScraper
from scraper.boards.rippling import RipplingScraper
from scraper.boards.shopify import ShopifyScraper
from scraper.boards.smartrecruiters import SmartRecruitersScraper
from scraper.boards.successfactors import SuccessFactorsScraper
from scraper.boards.teamtailor import TeamtailorScraper
from scraper.boards.tiktok import TikTokScraper
from scraper.boards.usajobs import UsajobsScraper
from scraper.boards.valve import ValveScraper
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
    PinpointScraper.source: PinpointScraper,
    JobviteScraper.source: JobviteScraper,
    JazzHrScraper.source: JazzHrScraper,
    GovernmentJobsScraper.source: GovernmentJobsScraper,
    ReliefwebScraper.source: ReliefwebScraper,
    OracleCloudScraper.source: OracleCloudScraper,
    SuccessFactorsScraper.source: SuccessFactorsScraper,
    AdpScraper.source: AdpScraper,
    PaylocityScraper.source: PaylocityScraper,
    IcimsScraper.source: IcimsScraper,
    IBMScraper.source: IBMScraper,
    AmazonScraper.source: AmazonScraper,
    AppleScraper.source: AppleScraper,
    MicrosoftScraper.source: MicrosoftScraper,
    ValveScraper.source: ValveScraper,
    TikTokScraper.source: TikTokScraper,
    NetflixScraper.source: NetflixScraper,
    GoogleScraper.source: GoogleScraper,
    EaScraper.source: EaScraper,
    AtlassianScraper.source: AtlassianScraper,
    ShopifyScraper.source: ShopifyScraper,
    PhenomScraper.source: PhenomScraper,
    JibeScraper.source: JibeScraper,
    MetaScraper.source: MetaScraper,
    JaneStreetScraper.source: JaneStreetScraper,
}
