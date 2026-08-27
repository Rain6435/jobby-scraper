from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.lever import LeverScraper, posted_days_from_epoch_ms
from scraper.config_types import LeverConfig

COMPANY: LeverConfig = {"name": "Palantir", "board": "lever", "company": "palantir"}
API = "https://api.lever.co/v0/postings/palantir"


def test_posted_days_from_epoch_ms() -> None:
    three_ago_ms = int((datetime.now(UTC) - timedelta(days=3, hours=2)).timestamp() * 1000)
    assert posted_days_from_epoch_ms(three_ago_ms) == 3
    assert posted_days_from_epoch_ms(None) is None
    assert posted_days_from_epoch_ms(0) is None


@responses.activate
def test_maps_jobs_with_dates_and_all_locations() -> None:
    created_ms = int((datetime.now(UTC) - timedelta(days=2)).timestamp() * 1000)
    responses.get(
        API,
        json=[
            {
                "id": "ac978161-6f46-4f6b-ad9e-a258e642751c",
                "text": "  Software Engineer  ",
                "hostedUrl": "https://jobs.lever.co/palantir/ac978161",
                "createdAt": created_ms,
                "categories": {
                    "location": "London, United Kingdom",
                    "allLocations": ["London, United Kingdom", "Remote UK"],
                },
                "descriptionPlain": "  Build great software.  ",
                "description": "<p>Build <b>great</b> software.</p>",
            },
        ],
    )

    jobs = LeverScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "palantir:ac978161-6f46-4f6b-ad9e-a258e642751c"
    assert job.title == "Software Engineer"
    assert job.locations == ["London, United Kingdom", "Remote UK"]
    assert job.location == "London, United Kingdom"
    assert job.url == "https://jobs.lever.co/palantir/ac978161"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "lever"
    assert job.description == "Build great software."  # descriptionPlain preferred


@responses.activate
def test_falls_back_to_stripped_html_without_plain_description() -> None:
    responses.get(
        API,
        json=[
            {
                "id": "x2",
                "text": "Dev",
                "hostedUrl": "u",
                "createdAt": None,
                "categories": {},
                "description": "<p>HTML only</p>",
            },
        ],
    )

    jobs = LeverScraper(COMPANY).fetch_jobs()

    assert jobs[0].description == "HTML only"


@responses.activate
def test_falls_back_when_no_all_locations_or_date() -> None:
    responses.get(
        API,
        json=[
            {
                "id": "x1",
                "text": "Dev",
                "hostedUrl": "u",
                "createdAt": None,
                "categories": {"location": "Remote"},
            },
        ],
    )

    jobs = LeverScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Remote"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_does_not_truncate_long_plain_description() -> None:
    """descriptionPlain used to be sliced at [:1500] here, independently of
    html_to_text's cap — so removing that cap alone left Lever truncated."""
    body = "Build great software. " * 500
    responses.get(
        API,
        json=[
            {
                "id": "abc",
                "text": "Engineer",
                "hostedUrl": "https://jobs.lever.co/palantir/abc",
                "categories": {"location": "Remote"},
                "descriptionPlain": body,
            },
        ],
    )

    jobs = LeverScraper(COMPANY).fetch_jobs()

    assert len(jobs[0].description) > 1500
    assert jobs[0].description == body.strip()
