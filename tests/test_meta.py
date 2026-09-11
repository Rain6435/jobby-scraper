import json

import responses
from requests import PreparedRequest

from scraper.boards.meta import (
    DOC_ID,
    GRAPHQL_URL,
    MetaScraper,
)
from scraper.config_types import MetaConfig

COMPANY: MetaConfig = {"name": "Meta", "board": "meta"}

SAMPLE_RESPONSE = {
    "data": {
        "job_search_with_featured_jobs_v2": {
            "all_jobs": [
                {
                    "id": "1456837426495499",
                    "title": "Infrastructure Accounting Manager",
                    "locations": ["Menlo Park, CA", "Seattle, WA"],
                    "teams": ["Finance", "Infrastructure"],
                    "sub_teams": ["Cloud Procurement"],
                },
                {
                    "id": "9876543210123456",
                    "title": "Research Scientist, AI",
                    "locations": ["New York, NY"],
                    "teams": ["AI Research"],
                    "sub_teams": ["FAIR"],
                },
                {
                    "id": "",
                    "title": "Invalid Job",
                },
            ]
        }
    }
}


@responses.activate
def test_fetch_jobs_success() -> None:
    responses.post(GRAPHQL_URL, json=SAMPLE_RESPONSE)

    scraper = MetaScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2

    j1 = jobs[0]
    assert j1.id == "meta:1456837426495499"
    assert j1.company == "Meta"
    assert j1.title == "Infrastructure Accounting Manager"
    assert j1.location == "Menlo Park, CA"
    assert j1.locations == ["Menlo Park, CA", "Seattle, WA"]
    assert j1.url == "https://www.metacareers.com/jobs/1456837426495499/"
    assert j1.source == "meta"
    assert "Teams: Finance, Infrastructure" in j1.description
    assert "Sub-teams: Cloud Procurement" in j1.description

    j2 = jobs[1]
    assert j2.id == "meta:9876543210123456"
    assert j2.company == "Meta"
    assert j2.title == "Research Scientist, AI"
    assert j2.location == "New York, NY"
    assert j2.locations == ["New York, NY"]
    assert j2.url == "https://www.metacareers.com/jobs/9876543210123456/"
    assert j2.source == "meta"
    assert "Teams: AI Research" in j2.description
    assert "Sub-teams: FAIR" in j2.description


@responses.activate
def test_fetch_jobs_with_query() -> None:
    def callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        body_str = request.body if isinstance(request.body, str) else ""
        assert f"doc_id={DOC_ID}" in body_str
        return (200, {"Content-Type": "application/json"}, json.dumps(SAMPLE_RESPONSE))

    responses.add_callback(
        responses.POST,
        GRAPHQL_URL,
        callback=callback,
        content_type="application/json",
    )

    scraper = MetaScraper({"name": "Meta", "board": "meta", "query": "AI"})
    jobs = scraper.fetch_jobs()
    assert len(jobs) == 2


@responses.activate
def test_fetch_jobs_network_error() -> None:
    responses.post(GRAPHQL_URL, status=500)

    scraper = MetaScraper(COMPANY)
    jobs = scraper.fetch_jobs()
    assert jobs == []
