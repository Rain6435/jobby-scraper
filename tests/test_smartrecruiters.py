from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.smartrecruiters import (
    PAGE_LIMIT,
    SmartRecruitersListResponse,
    SmartRecruitersScraper,
)
from scraper.config_types import SmartRecruitersConfig
from scraper.models import Job

COMPANY: SmartRecruitersConfig = {"name": "Acme", "board": "smartrecruiters", "company": "acme"}
API = "https://api.smartrecruiters.com/v1/companies/acme/postings"


def detail_url(posting_id: str) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/acme/postings/{posting_id}"


@responses.activate
def test_maps_jobs_with_dates_and_detail_fetch() -> None:
    released = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    responses.get(API, json={
        "totalFound": 1,
        "content": [{
            "id": "744000137613800",
            "name": "  Senior Security Engineer  ",
            "releasedDate": released,
            "location": {"city": "Poland", "region": "REMOTE", "country": "pl",
                          "fullLocation": "Poland, REMOTE, Poland"},
        }],
    })
    responses.get(detail_url("744000137613800"), json={
        "postingUrl": "https://jobs.smartrecruiters.com/acme/744000137613800-senior-security-engineer",
        "jobAd": {"sections": {"jobDescription": {"text": "<p>Secure things.</p>"}}},
    })

    jobs = SmartRecruitersScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "acme:744000137613800"
    assert job.title == "Senior Security Engineer"
    assert job.locations == ["Poland, REMOTE, Poland"]
    assert job.location == "Poland, REMOTE, Poland"
    assert job.url == "https://jobs.smartrecruiters.com/acme/744000137613800-senior-security-engineer"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "smartrecruiters"
    assert job.description == "Secure things."


@responses.activate
def test_falls_back_when_no_location_or_date() -> None:
    responses.get(API, json={
        "totalFound": 1,
        "content": [{"id": "x1", "name": "Dev", "releasedDate": ""}],
    })
    responses.get(detail_url("x1"), json={"postingUrl": "u", "jobAd": {}})

    jobs = SmartRecruitersScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == []
    assert jobs[0].location == ""
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""


@responses.activate
def test_description_and_url_empty_on_detail_failure() -> None:
    responses.get(API, json={
        "totalFound": 1,
        "content": [{"id": "x1", "name": "Dev", "releasedDate": ""}],
    })
    responses.get(detail_url("x1"), status=500)

    jobs = SmartRecruitersScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""
    assert jobs[0].url == ""


@responses.activate
def test_skips_detail_fetch_for_job_already_in_previous_snapshot() -> None:
    responses.get(API, json={
        "totalFound": 1,
        "content": [{"id": "x1", "name": "Dev", "releasedDate": ""}],
    })
    # No detail-endpoint mock registered — a call here would fail the test.

    previous = {"acme:x1": Job(
        id="acme:x1", company="Acme", title="Old title", location="",
        url="https://example.com/cached", posted_on="", source="smartrecruiters",
        description="Cached description.",
    )}

    jobs = SmartRecruitersScraper(COMPANY, previous=previous).fetch_jobs()

    assert len(responses.calls) == 1  # list only
    assert jobs[0].description == "Cached description."
    assert jobs[0].url == "https://example.com/cached"


@responses.activate
def test_fetches_detail_for_job_not_in_previous_snapshot() -> None:
    responses.get(API, json={
        "totalFound": 1,
        "content": [{"id": "x1", "name": "Dev", "releasedDate": ""}],
    })
    responses.get(detail_url("x1"), json={
        "postingUrl": "https://example.com/fresh",
        "jobAd": {"sections": {"jobDescription": {"text": "<p>Freshly fetched.</p>"}}},
    })

    jobs = SmartRecruitersScraper(COMPANY, previous={}).fetch_jobs()

    assert jobs[0].description == "Freshly fetched."
    assert jobs[0].url == "https://example.com/fresh"


@responses.activate
def test_paginates_across_pages() -> None:
    def page(n: int, count: int) -> SmartRecruitersListResponse:
        return {
            "totalFound": PAGE_LIMIT + 3,
            "content": [
                {"id": f"id-{n}-{i}", "name": f"Job {n}-{i}", "releasedDate": ""}
                for i in range(count)
            ],
        }

    responses.get(API, json=page(0, PAGE_LIMIT))
    responses.get(API, json=page(1, 3))
    for i in range(PAGE_LIMIT):
        responses.get(detail_url(f"id-0-{i}"), json={"postingUrl": "u", "jobAd": {}})
    for i in range(3):
        responses.get(detail_url(f"id-1-{i}"), json={"postingUrl": "u", "jobAd": {}})

    jobs = SmartRecruitersScraper(COMPANY).fetch_jobs()

    assert len(jobs) == PAGE_LIMIT + 3
    list_calls = [
        c for c in responses.calls
        if c.request.url is not None and c.request.url.split("?")[0] == API
    ]
    assert len(list_calls) == 2
    second_call_url = list_calls[1].request.url
    assert second_call_url is not None
    assert f"offset={PAGE_LIMIT}" in second_call_url
