import json
from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.paylocity import PaylocityScraper
from scraper.config_types import PaylocityConfig

COMPANY: PaylocityConfig = {
    "name": "Apex Healthcare",
    "board": "paylocity",
    "guid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
}
FEED_URL = "https://recruiting.paylocity.com/recruiting/v2/api/feed/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@responses.activate
def test_maps_paylocity_jobs() -> None:
    posted = (datetime.now(UTC) - timedelta(days=4)).isoformat()
    mock_data = {
        "displayName": "Apex Healthcare",
        "jobs": [
            {
                "jobId": 771122,
                "publicJobId": 771122,
                "jobTitle": "Clinical Data Analyst",
                "jobDescription": "<p>Analyze healthcare metrics and <em>clinical outcomes</em>.</p>",
                "applyUrl": "https://recruiting.paylocity.com/recruiting/jobs/Details/771122/Apex/Clinical-Data-Analyst",
                "jobLocation": {
                    "city": "Denver",
                    "state": "CO",
                    "zip": "80202",
                    "country": "US",
                },
                "postedDate": posted,
                "department": "Analytics",
            }
        ],
    }

    responses.get(FEED_URL, body=json.dumps(mock_data), content_type="application/json")

    jobs = PaylocityScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "apex-healthcare:771122"
    assert j.company == "Apex Healthcare"
    assert j.title == "Clinical Data Analyst"
    assert j.location == "Denver, CO, US"
    assert j.locations == ["Denver, CO, US"]
    assert j.posted_days == 4
    assert j.posted_on == "4 days ago"
    assert (
        j.url
        == "https://recruiting.paylocity.com/recruiting/jobs/Details/771122/Apex/Clinical-Data-Analyst"
    )
    assert "Analyze healthcare metrics and clinical outcomes." in j.description
    assert j.source == "paylocity"


@responses.activate
def test_handles_empty_paylocity_feed() -> None:
    responses.get(FEED_URL, body=json.dumps({"jobs": []}), content_type="application/json")

    jobs = PaylocityScraper(COMPANY).fetch_jobs()
    assert jobs == []
