import responses

from scraper.boards.atlassian import (
    LISTINGS_URL,
    AtlassianScraper,
    clean_atlassian_location,
    parse_atlassian_date,
)
from scraper.config_types import AtlassianConfig

COMPANY: AtlassianConfig = {"name": "Atlassian", "board": "atlassian"}


def _sample_postings() -> list[dict[str, object]]:
    return [
        {
            "id": 27075,
            "title": "Principal Engineer - Data Platform",
            "category": "Engineering",
            "type": "Full-Time",
            "locations": [
                "Bengaluru - India -   Bengaluru,  560071 India",
                "Remote - India - Remote",
                "Remote - Remote",
            ],
            "overview": "<p>Overview of Data Platform role.</p>",
            "responsibilities": "<p>Lead architecture of batch and streaming pipelines.</p>",
            "qualifications": "<p>10+ years distributed systems.</p>",
            "payRanges": "<p>Base pay: $180k - $220k</p>",
            "compensation": "<p>Competitive equity and bonus.</p>",
            "applyUrl": "https://careers-apac-atlassian.icims.com/jobs/27075/job?mode=apply",
            "portalJobPost": {
                "id": 27075,
                "portalId": 242,
                "portalUrl": "https://careers-apac-atlassian.icims.com/jobs/27075/principal-engineer/job",
                "updatedDate": "2026-09-07 05:17 AM",
            },
        },
        {
            "id": 25583,
            "title": "Account Executive - Japanese Speaking",
            "category": "Sales",
            "type": "Full-Time",
            "locations": [
                "Austin - United States -   Austin, Texas 78702 United States",
                "Remote - Americas - Remote",
            ],
            "overview": "<p>Sales overview.</p>",
            "responsibilities": "<p>Close enterprise accounts.</p>",
            "qualifications": "<p>5+ years B2B SaaS.</p>",
            "applyUrl": "https://globalcareers-atlassian.icims.com/jobs/25583/job?mode=apply",
            "portalJobPost": {
                "id": 25583,
                "portalId": 17,
                "portalUrl": "https://globalcareers-atlassian.icims.com/jobs/25583/account-executive/job",
                "updatedDate": "2026-09-08 01:00 AM",
            },
        },
        {
            "id": 26001,
            "title": "Staff Product Designer",
            "category": "Design",
            "type": "Full-Time",
            "locations": [
                "Remote - Remote",
            ],
            "overview": "<p>Design systems for Jira.</p>",
            "responsibilities": "<p>Design intuitive user flows.</p>",
            "qualifications": "<p>Portfolio demonstrating complex SaaS workflows.</p>",
            "portalJobPost": {
                "id": 26001,
                "portalId": 17,
                "portalUrl": "https://globalcareers-atlassian.icims.com/jobs/26001/staff-product-designer/job",
                "updatedDate": "2026-09-01 10:00 AM",
            },
        },
    ]


@responses.activate
def test_fetches_jobs_successfully():
    responses.add(
        responses.GET,
        LISTINGS_URL,
        json=_sample_postings(),
        status=200,
    )

    scraper = AtlassianScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 3

    j1 = jobs[0]
    assert j1.id == "atlassian:27075"
    assert j1.title == "Principal Engineer - Data Platform"
    assert j1.company == "Atlassian"
    assert j1.location == "Bengaluru, India"
    assert j1.locations == ["Bengaluru, India", "Remote, India", "Remote"]
    assert j1.url == "https://careers-apac-atlassian.icims.com/jobs/27075/principal-engineer/job"
    assert j1.source == "atlassian"
    assert j1.posted_date == "2026-09-07"
    assert j1.posted_days is not None
    assert "Overview of Data Platform role." in j1.description
    assert "Lead architecture of batch and streaming pipelines." in j1.description
    assert "10+ years distributed systems." in j1.description
    assert "Base pay: $180k - $220k" in j1.description

    j3 = jobs[2]
    assert j3.id == "atlassian:26001"
    assert j3.location == "Remote"
    assert j3.locations == ["Remote"]


@responses.activate
def test_filters_by_category():
    responses.add(
        responses.GET,
        LISTINGS_URL,
        json=_sample_postings(),
        status=200,
    )

    company: AtlassianConfig = {
        "name": "Atlassian",
        "board": "atlassian",
        "category": "Engineering",
    }
    scraper = AtlassianScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "atlassian:27075"


@responses.activate
def test_filters_by_location():
    responses.add(
        responses.GET,
        LISTINGS_URL,
        json=_sample_postings(),
        status=200,
    )

    company: AtlassianConfig = {"name": "Atlassian", "board": "atlassian", "location": "Austin"}
    scraper = AtlassianScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "atlassian:25583"


@responses.activate
def test_filters_by_keyword():
    responses.add(
        responses.GET,
        LISTINGS_URL,
        json=_sample_postings(),
        status=200,
    )

    company: AtlassianConfig = {"name": "Atlassian", "board": "atlassian", "keyword": "Designer"}
    scraper = AtlassianScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "atlassian:26001"


@responses.activate
def test_handles_empty_response():
    responses.add(
        responses.GET,
        LISTINGS_URL,
        json=[],
        status=200,
    )

    scraper = AtlassianScraper(COMPANY)
    jobs = scraper.fetch_jobs()
    assert jobs == []


def test_clean_atlassian_location():
    assert (
        clean_atlassian_location("Austin - United States -   Austin, Texas 78702 United States")
        == "Austin, United States"
    )
    assert clean_atlassian_location("Remote - Americas - Remote") == "Remote, Americas"
    assert clean_atlassian_location("Remote - Remote") == "Remote"
    assert clean_atlassian_location("Remote - France -     France") == "Remote, France"
    assert (
        clean_atlassian_location(
            "Mountain View - United States or Remote - Mountain View, California"
        )
        == "Mountain View, United States or Remote"
    )
    assert (
        clean_atlassian_location("Singapore - Singapore -   Central Singapore  Singapore")
        == "Singapore"
    )
    assert clean_atlassian_location("") == "Remote"


def test_parse_atlassian_date():
    dt = parse_atlassian_date("2026-09-08 01:00 AM")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 8
    assert dt.hour == 1

    assert parse_atlassian_date(None) is None
    assert parse_atlassian_date("invalid") is None
