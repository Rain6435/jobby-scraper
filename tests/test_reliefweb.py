import json
from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.reliefweb import ReliefwebScraper
from scraper.config_types import ReliefwebConfig

COMPANY: ReliefwebConfig = {
    "name": "ReliefWeb",
    "board": "reliefweb",
}
API = "https://api.reliefweb.int/v2/jobs"


@responses.activate
def test_maps_reliefweb_jobs_and_source_organization() -> None:
    created = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    mock_data = {
        "totalCount": 1,
        "count": 1,
        "data": [
            {
                "id": "rw-4019283",
                "fields": {
                    "title": "Emergency Health Coordinator",
                    "url": "https://reliefweb.int/job/4019283/emergency-health-coordinator",
                    "body": "<p>Oversee clinical operations in disaster zone.</p>",
                    "date": {"created": created},
                    "source": [{"name": "UNICEF", "shortname": "UNICEF"}],
                    "country": [{"name": "Sudan", "iso3": "sdn"}],
                    "city": [{"name": "Port Sudan"}],
                },
            }
        ],
    }
    responses.get(API, body=json.dumps(mock_data), content_type="application/json")

    jobs = ReliefwebScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "reliefweb:rw-4019283"
    assert job.company == "UNICEF"
    assert job.title == "Emergency Health Coordinator"
    assert job.url == "https://reliefweb.int/job/4019283/emergency-health-coordinator"
    assert job.location == "Port Sudan, Sudan"
    assert job.locations == ["Port Sudan, Sudan"]
    assert job.posted_days == 1
    assert job.posted_on == "Yesterday"
    assert job.source == "reliefweb"
    assert "Oversee clinical operations in disaster zone." in job.description


@responses.activate
def test_falls_back_to_company_name_when_source_missing() -> None:
    mock_data = {
        "totalCount": 1,
        "count": 1,
        "data": [
            {
                "id": "9988",
                "fields": {
                    "title": "Logistics Assistant",
                    "url": "https://reliefweb.int/job/9988",
                    "body": "Logistics operations",
                    "country": [{"name": "Jordan"}],
                },
            }
        ],
    }
    responses.get(API, body=json.dumps(mock_data), content_type="application/json")

    jobs = ReliefwebScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].company == "ReliefWeb"
    assert jobs[0].location == "Jordan"
    assert jobs[0].posted_days is None
