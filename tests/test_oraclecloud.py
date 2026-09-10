import json
from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.oraclecloud import OracleCloudScraper, OracleResponse
from scraper.config_types import OracleCloudConfig

COMPANY: OracleCloudConfig = {
    "name": "Enterprise Corp",
    "board": "oraclecloud",
    "tenant": "enterprise.fa.ocs",
    "site_number": "CX_1001",
}
API_BASE = "https://enterprise.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"


@responses.activate
def test_maps_oraclecloud_jobs_with_pagination() -> None:
    posted = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    page1: OracleResponse = {
        "items": [
            {
                "Id": 101,
                "Title": "Staff Software Engineer",
                "PrimaryLocation": "Seattle, WA, United States",
                "PostedDate": posted,
                "ExternalDescriptionStr": "<p>Build cloud services.</p>",
                "WorkLocation": "Seattle HQ",
            }
        ],
        "count": 1,
        "hasMore": True,
        "limit": 25,
        "offset": 0,
    }
    page2: OracleResponse = {
        "items": [
            {
                "Id": 102,
                "Title": "Product Manager",
                "PrimaryLocation": "Austin, TX, United States",
                "PostedDate": posted,
                "ExternalDescriptionStr": "<p>Lead roadmap.</p>",
            }
        ],
        "count": 1,
        "hasMore": False,
        "limit": 25,
        "offset": 1,
    }

    responses.get(
        f"{API_BASE}?finder=findReqs%3BsiteNumber%3DCX_1001&limit=25&offset=0&onlyData=true&expand=requisitionList",
        body=json.dumps(page1),
        content_type="application/json",
    )
    responses.get(
        f"{API_BASE}?finder=findReqs%3BsiteNumber%3DCX_1001%2Coffset%3D1&limit=25&offset=1&onlyData=true&expand=requisitionList",
        body=json.dumps(page2),
        content_type="application/json",
    )

    jobs = OracleCloudScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 2
    j1 = jobs[0]
    assert j1.id == "enterprise-corp:101"
    assert j1.title == "Staff Software Engineer"
    assert j1.location == "Seattle, WA, United States"
    assert j1.locations == ["Seattle, WA, United States"]
    assert j1.posted_days == 2
    assert j1.posted_on == "2 days ago"
    assert (
        j1.url
        == "https://enterprise.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/101"
    )
    assert "Build cloud services." in j1.description

    j2 = jobs[1]
    assert j2.id == "enterprise-corp:102"
    assert j2.title == "Product Manager"


@responses.activate
def test_handles_nested_requisition_list() -> None:
    posted = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    nested_resp: OracleResponse = {
        "items": [
            {
                "requisitionList": [
                    {
                        "Id": 201,
                        "Title": "Senior Wind Energy Specialist",
                        "PrimaryLocation": "Longueuil, QC, Canada",
                        "PostedDate": posted,
                        "ExternalDescriptionStr": "<p>Oversee renewable installations.</p>",
                    }
                ]
            }
        ],
        "count": 1,
        "hasMore": False,
        "limit": 25,
        "offset": 0,
    }
    responses.get(
        f"{API_BASE}?finder=findReqs%3BsiteNumber%3DCX_1001&limit=25&offset=0&onlyData=true&expand=requisitionList",
        body=json.dumps(nested_resp),
        content_type="application/json",
    )

    jobs = OracleCloudScraper(COMPANY).fetch_jobs()
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Wind Energy Specialist"
    assert jobs[0].location == "Longueuil, QC, Canada"


@responses.activate
def test_handles_empty_and_fallback_fields() -> None:
    empty_resp: OracleResponse = {"items": [], "count": 0, "hasMore": False}
    responses.get(
        f"{API_BASE}?finder=findReqs%3BsiteNumber%3DCX_1001&limit=25&offset=0&onlyData=true&expand=requisitionList",
        body=json.dumps(empty_resp),
        content_type="application/json",
    )

    jobs = OracleCloudScraper(COMPANY).fetch_jobs()
    assert jobs == []
