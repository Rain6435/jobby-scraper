import responses

from scraper.boards.rippling import RipplingScraper, PAGE_SIZE
from scraper.models import Job

COMPANY = {"name": "Octasic", "board": "rippling", "board_id": "octasic-inc"}
API = "https://ats.rippling.com/api/v2/board/octasic-inc/jobs"


def detail_url(job_id):
    return f"https://ats.rippling.com/api/v2/board/octasic-inc/jobs/{job_id}"


@responses.activate
def test_maps_jobs_with_structured_locations_and_no_date():
    responses.get(API, json={
        "items": [{
            "id": "83fb1287-uuid",
            "name": "  Backend Developer  ",
            "url": "https://ats.rippling.com/octasic-inc/jobs/83fb1287-uuid",
            "locations": [{
                "name": "Hybrid (Montreal, QC, CA)",  # raw name has the "CA" collision
                "city": "Montreal", "state": "QC", "country": "Canada",
            }],
        }],
        "totalPages": 1,
    })
    responses.get(detail_url("83fb1287-uuid"), json={
        "description": {"role": "<p>Ship backend features.</p>", "company": "<p>About us.</p>"}
    })

    jobs = RipplingScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "octasic:83fb1287-uuid"
    assert job.title == "Backend Developer"
    # Built from structured fields — country spelled out so "CA" isn't read as California.
    assert job.locations == ["Montreal, QC, Canada"]
    assert job.location == "Montreal, QC, Canada"
    assert job.url == "https://ats.rippling.com/octasic-inc/jobs/83fb1287-uuid"
    assert job.posted_days is None       # date is detail-only — skipped
    assert job.posted_on == ""
    assert job.source == "rippling"
    assert job.description == "Ship backend features."


@responses.activate
def test_description_handles_plain_string_shape():
    """Some Rippling boards may return description as a plain string instead
    of the usual {"role": ..., "company": ...} object — handle both."""
    responses.get(API, json={
        "items": [{"id": "x2", "name": "Dev", "url": "u", "locations": []}],
        "totalPages": 1,
    })
    responses.get(detail_url("x2"), json={"description": "<p>Plain string role.</p>"})

    jobs = RipplingScraper(COMPANY).fetch_jobs()

    assert jobs[0].description == "Plain string role."


@responses.activate
def test_description_empty_on_detail_failure():
    responses.get(API, json={
        "items": [{"id": "x1", "name": "Dev", "url": "u", "locations": []}],
        "totalPages": 1,
    })
    responses.get(detail_url("x1"), status=500)

    jobs = RipplingScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""


@responses.activate
def test_skips_detail_fetch_for_job_already_in_previous_snapshot():
    responses.get(API, json={
        "items": [{"id": "x1", "name": "Dev", "url": "u", "locations": []}],
        "totalPages": 1,
    })
    # No detail-endpoint mock registered — a call here would fail the test.

    previous = {"octasic:x1": Job(
        id="octasic:x1", company="Octasic", title="Dev (old)", location="",
        url="u", posted_on="", source="rippling",
        description="Cached description.",
    )}

    jobs = RipplingScraper(COMPANY, previous=previous).fetch_jobs()

    list_calls = [
        c for c in responses.calls
        if c.request.url is not None and c.request.url.split("?")[0] == API
    ]
    assert len(responses.calls) == len(list_calls)  # only the list call, no detail
    assert jobs[0].description == "Cached description."


@responses.activate
def test_fetches_detail_for_job_not_in_previous_snapshot():
    responses.get(API, json={
        "items": [{"id": "x1", "name": "Dev", "url": "u", "locations": []}],
        "totalPages": 1,
    })
    responses.get(detail_url("x1"), json={"description": "<p>Freshly fetched.</p>"})

    jobs = RipplingScraper(COMPANY, previous={}).fetch_jobs()

    assert jobs[0].description == "Freshly fetched."


@responses.activate
def test_paginates_across_pages():
    def page(n, count):
        return {
            "items": [
                {"id": f"id-{n}-{i}", "name": f"Job {n}-{i}", "url": "u",
                 "locations": [{"name": "Montreal, QC"}]}
                for i in range(count)
            ],
            "totalPages": 2,
        }

    responses.get(API, json=page(0, PAGE_SIZE))
    responses.get(API, json=page(1, 3))
    for i in range(PAGE_SIZE):
        responses.get(detail_url(f"id-0-{i}"), json={"description": ""})
    for i in range(3):
        responses.get(detail_url(f"id-1-{i}"), json={"description": ""})

    jobs = RipplingScraper(COMPANY).fetch_jobs()

    assert len(jobs) == PAGE_SIZE + 3
    list_calls = [
        c for c in responses.calls
        if c.request.url is not None and c.request.url.split("?")[0] == API
    ]
    assert len(list_calls) == 2
    second_call_url = list_calls[1].request.url
    assert second_call_url is not None
    assert "page=1" in second_call_url
