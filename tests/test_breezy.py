from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.breezy import BreezyScraper
from scraper.config_types import BreezyConfig

COMPANY: BreezyConfig = {"name": "Vosyn", "board": "breezy", "company": "vosyn"}
API = "https://vosyn.breezy.hr/json"


@responses.activate
def test_maps_jobs_with_dates_and_multi_locations() -> None:
    published = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    responses.get(
        API,
        json=[
            {
                "id": "3a11757fffb7",
                "name": "  AI Application Builder  ",
                "url": "https://vosyn.breezy.hr/p/3a11757fffb7",
                "published_date": published,
                "location": {"name": "Etobicoke, ON"},
                "locations": [{"name": "Etobicoke, ON"}, {"name": "Remote"}],
            },
        ],
    )

    jobs = BreezyScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "vosyn:3a11757fffb7"
    assert job.title == "AI Application Builder"
    assert job.locations == ["Etobicoke, ON", "Remote"]
    assert job.location == "Etobicoke, ON"
    assert job.url == "https://vosyn.breezy.hr/p/3a11757fffb7"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "breezy"


@responses.activate
def test_falls_back_to_single_location_without_locations_list() -> None:
    responses.get(
        API,
        json=[
            {
                "id": "x1",
                "name": "Dev",
                "url": "u",
                "published_date": "",
                "location": {"name": "Remote"},
                "locations": [],
            },
        ],
    )

    jobs = BreezyScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Remote"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""


@responses.activate
def test_description_always_empty_no_public_source() -> None:
    """Breezy has no public API exposing a job description (list JSON lacks
    it, and the per-job detail endpoints all return the SPA HTML shell, not
    JSON — confirmed live). This is intentional, not a gap to fill later."""
    responses.get(
        API,
        json=[
            {
                "id": "x1",
                "name": "Dev",
                "url": "u",
                "published_date": "",
                "location": {"name": "Remote"},
                "locations": [],
            },
        ],
    )

    jobs = BreezyScraper(COMPANY).fetch_jobs()

    assert jobs[0].description == ""
