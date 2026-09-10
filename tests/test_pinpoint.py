import json
from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.pinpoint import PinpointScraper
from scraper.config_types import PinpointConfig

COMPANY: PinpointConfig = {
    "name": "Taxfix",
    "board": "pinpoint",
    "company": "taxfix",
}
API = "https://taxfix.pinpointhq.com/postings.json"


@responses.activate
def test_maps_pinpoint_jobs_with_iso_dates_and_locations() -> None:
    created = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    mock_data = {
        "data": [
            {
                "id": 12345,
                "title": "Senior Software Engineer",
                "url": "https://taxfix.pinpointhq.com/postings/12345",
                "created_at": created,
                "description": "<p>We are looking for a <strong>Senior Engineer</strong>.</p>",
                "locations": [
                    {"name": "Berlin HQ", "city": "Berlin", "country": "Germany"},
                    {"name": "London Hub", "city": "London", "country": "UK"},
                ],
            }
        ]
    }
    responses.get(API, body=json.dumps(mock_data), content_type="application/json")

    jobs = PinpointScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "taxfix:12345"
    assert job.company == "Taxfix"
    assert job.title == "Senior Software Engineer"
    assert job.url == "https://taxfix.pinpointhq.com/postings/12345"
    assert job.posted_days == 3
    assert job.posted_on == "3 days ago"
    assert job.location == "Berlin, Germany"
    assert job.locations == ["Berlin, Germany", "London, UK"]
    assert job.source == "pinpoint"
    assert "We are looking for a Senior Engineer." in job.description


@responses.activate
def test_handles_flat_list_and_string_locations() -> None:
    mock_data = [
        {
            "id": "abc-99",
            "title": "Product Designer",
            "url": "https://taxfix.pinpointhq.com/postings/abc-99",
            "description": "Designing products",
            "location": "Remote - US",
        }
    ]
    responses.get(API, body=json.dumps(mock_data), content_type="application/json")

    jobs = PinpointScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "taxfix:abc-99"
    assert jobs[0].location == "Remote - US"
    assert jobs[0].locations == ["Remote - US"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
