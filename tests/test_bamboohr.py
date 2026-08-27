import responses

from scraper.boards.bamboohr import BambooHRScraper
from scraper.config_types import BambooHrConfig
from scraper.models import Job

COMPANY: BambooHrConfig = {"name": "Euna", "board": "bamboohr", "company": "euna"}
LIST_URL = "https://euna.bamboohr.com/careers/list"


def detail_url(job_id: str) -> str:
    return f"https://euna.bamboohr.com/careers/{job_id}/detail"


@responses.activate
def test_maps_list_rows_with_constructed_url_and_no_date() -> None:
    responses.get(LIST_URL, json={"result": [
        {
            "id": "562",
            "jobOpeningName": "Software Developer",
            "location": {"city": "Oakville", "state": "Ontario"},
        },
    ]})
    responses.get(detail_url("562"), json={
        "result": {"jobOpening": {"description": "<p>Build features.</p>"}}
    })

    jobs = BambooHRScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "euna:562"
    assert job.title == "Software Developer"
    assert job.location == "Oakville, Ontario"
    assert job.locations == ["Oakville, Ontario"]
    assert job.url == "https://euna.bamboohr.com/careers/562"   # built, no detail call needed for URL
    assert job.posted_days is None
    assert job.posted_on == ""
    assert job.source == "bamboohr"
    assert job.description == "Build features."


@responses.activate
def test_handles_missing_location_parts() -> None:
    responses.get(LIST_URL, json={"result": [
        {"id": "9", "jobOpeningName": "Remote Role", "location": {"city": "Toronto"}},
    ]})
    responses.get(detail_url("9"), json={"result": {"jobOpening": {}}})

    jobs = BambooHRScraper(COMPANY).fetch_jobs()

    assert jobs[0].location == "Toronto"
    assert jobs[0].locations == ["Toronto"]
    assert jobs[0].description == ""


@responses.activate
def test_description_empty_on_detail_failure() -> None:
    responses.get(LIST_URL, json={"result": [
        {"id": "9", "jobOpeningName": "Remote Role", "location": {}},
    ]})
    responses.get(detail_url("9"), status=500)

    jobs = BambooHRScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""


@responses.activate
def test_skips_detail_fetch_for_job_already_in_previous_snapshot() -> None:
    responses.get(LIST_URL, json={"result": [
        {"id": "562", "jobOpeningName": "Software Developer", "location": {"city": "Oakville"}},
    ]})
    # No detail-endpoint mock registered — a call here would fail the test.

    previous = {"euna:562": Job(
        id="euna:562", company="Euna", title="Old title", location="",
        url="u", posted_on="", source="bamboohr",
        description="Cached description.",
    )}

    jobs = BambooHRScraper(COMPANY, previous=previous).fetch_jobs()

    assert len(responses.calls) == 1  # list only
    assert jobs[0].description == "Cached description."


@responses.activate
def test_fetches_detail_for_job_not_in_previous_snapshot() -> None:
    responses.get(LIST_URL, json={"result": [
        {"id": "562", "jobOpeningName": "Software Developer", "location": {"city": "Oakville"}},
    ]})
    responses.get(detail_url("562"), json={
        "result": {"jobOpening": {"description": "<p>Freshly fetched.</p>"}}
    })

    jobs = BambooHRScraper(COMPANY, previous={}).fetch_jobs()

    assert jobs[0].description == "Freshly fetched."
