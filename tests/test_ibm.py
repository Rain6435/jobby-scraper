import responses

from scraper.boards.ibm import (
    API,
    IBMHit,
    IBMHitsObject,
    IBMJobSource,
    IBMResponse,
    IBMScraper,
    IBMTotal,
)
from scraper.config_types import IBMConfig

COMPANY: IBMConfig = {"name": "IBM", "board": "ibm"}


def _hit(
    job_id: str = "abc123",
    title: str = "Software Engineer",
    url: str = "https://careers.ibm.com/careers/JobDetail?jobId=99999",
    location: str = "Toronto, CA",
    description: str = "Build great things at IBM.",
) -> IBMHit:
    src = IBMJobSource(
        title=f"  {title}  ",
        url=url,
        field_keyword_19=location,
        field_keyword_08="Software Engineering",
        field_keyword_17="Hybrid",
        field_keyword_18="Mid Level",
        description=description,
    )
    return IBMHit(_id=job_id, _source=src)


def _total(value: int) -> IBMTotal:
    return IBMTotal(value=value, relation="eq")


def _page(hits: list[IBMHit], total: int | None = None) -> IBMResponse:
    t = _total(total if total is not None else len(hits))
    return IBMResponse(hits=IBMHitsObject(hits=hits, total=t))


@responses.activate
def test_maps_a_hit() -> None:
    responses.post(API, json=_page([_hit()]))

    jobs = IBMScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "ibm:abc123"
    assert job.company == "IBM"
    assert job.title == "Software Engineer"
    assert job.location == "Toronto, CA"
    assert job.locations == ["Toronto, CA"]
    assert job.url == "https://careers.ibm.com/careers/JobDetail?jobId=99999"
    assert job.source == "ibm"
    assert job.description == "Build great things at IBM."
    assert job.posted_days is None


@responses.activate
def test_strips_whitespace_from_title() -> None:
    responses.post(API, json=_page([_hit(title="  Data Scientist  ")]))

    jobs = IBMScraper(COMPANY).fetch_jobs()

    assert jobs[0].title == "Data Scientist"


@responses.activate
def test_empty_location_produces_empty_locations_list() -> None:
    hit = _hit(location="")
    responses.post(API, json=_page([hit]))

    jobs = IBMScraper(COMPANY).fetch_jobs()

    assert jobs[0].location == ""
    assert jobs[0].locations == []


@responses.activate
def test_paginates_until_all_jobs_fetched() -> None:
    responses.post(API, json=_page([_hit("1"), _hit("2")], total=3))
    responses.post(API, json=_page([_hit("3")], total=3))

    jobs = IBMScraper(COMPANY).fetch_jobs()

    assert {j.id for j in jobs} == {"ibm:1", "ibm:2", "ibm:3"}
    assert len(responses.calls) == 2


@responses.activate
def test_stops_on_empty_hits() -> None:
    responses.post(API, json=_page([], total=0))

    jobs = IBMScraper(COMPANY).fetch_jobs()

    assert jobs == []
    assert len(responses.calls) == 1
