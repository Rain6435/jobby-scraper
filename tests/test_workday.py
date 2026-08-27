import json
import re
from pathlib import Path
from typing import TypedDict, cast

import responses

from scraper.boards.workday import (
    PAGE_SIZE,
    WorkdayJobDetailResponse,
    WorkdayJobPosting,
    WorkdayJobPostingsResponse,
    WorkdayScraper,
    parse_posted_days,
)
from scraper.config_types import WorkdayConfig
from scraper.models import Job

FIXTURE: WorkdayJobPostingsResponse = json.loads(
    (Path(__file__).parent / "fixtures" / "workday_response.json").read_text(encoding="utf-8")
)

COMPANY: WorkdayConfig = {
    "name": "CAE",
    "board": "workday",
    "url": "https://cae.wd3.myworkdayjobs.com/wday/cxs/cae/career/jobs",
    "careers_base": "https://cae.wd3.myworkdayjobs.com/en-US/career",
}
DETAIL_BASE = "https://cae.wd3.myworkdayjobs.com/wday/cxs/cae/career"
DETAIL_RE = re.compile(re.escape(DETAIL_BASE) + r"/.*")


class WorkdayJobPostingsRequest(TypedDict):
    appliedFacets: dict[str, object]
    limit: int
    offset: int
    searchText: str


def posting(
    title: str = "Job", path: str = "/job/X/Job-1", loc: str = "Montreal",
    posted: str = "Posted Today", rid: str = "JR-1",
) -> WorkdayJobPosting:
    return {
        "title": title,
        "externalPath": path,
        "locationsText": loc,
        "postedOn": posted,
        "bulletFields": [rid],
    }


def mock_any_detail(json_body: WorkdayJobDetailResponse | None = None) -> None:
    """Mock every detail-endpoint GET this test's scraper might issue (now
    unconditional for every posting, not just multi-location ones)."""
    responses.add(
        responses.GET, DETAIL_RE,
        json=json_body or {"jobPostingInfo": {}},
    )


def test_parse_posted_days() -> None:
    assert parse_posted_days("Posted Today") == 0
    assert parse_posted_days("Posted Yesterday") == 1
    assert parse_posted_days("Posted 3 Days Ago") == 3
    assert parse_posted_days("Posted 30+ Days Ago") == 30
    assert parse_posted_days("whenever") is None


@responses.activate
def test_parses_postings_with_no_age_filtering() -> None:
    responses.post(COMPANY["url"], json=FIXTURE)
    mock_any_detail({"jobPostingInfo": {"jobDescription": "<p>Build things.</p>"}})

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    # Fixture has 3 postings, including one "Posted 30+ Days Ago" — all survive,
    # no age-based cutoff.
    assert [j.title for j in jobs] == [
        "Software Engineer Intern", "Data Rotation Program", "Senior Staff Architect",
    ]
    job = jobs[0]
    assert job.id == "cae:JR-100001"
    assert job.company == "CAE"
    assert job.location == "Montreal, Canada"
    assert job.locations == ["Montreal, Canada"]
    assert job.posted_days == 2
    assert job.url == (
        "https://cae.wd3.myworkdayjobs.com/en-US/career"
        "/job/Montreal/Software-Engineer-Intern_JR-100001"
    )
    assert job.source == "workday"
    assert job.description == "Build things."


@responses.activate
def test_paginates_until_total() -> None:
    def page(offset: int, total: int, count: int) -> WorkdayJobPostingsResponse:
        return {
            "total": total,
            "jobPostings": [
                posting(title=f"Job {offset + i}", path=f"/job/X/Job-{offset + i}",
                        rid=f"JR-{offset + i}")
                for i in range(count)
            ],
        }

    total = PAGE_SIZE + 5  # two pages
    responses.post(COMPANY["url"], json=page(0, total, PAGE_SIZE))
    # Real Workday only reports "total" on the first page; later pages say 0.
    responses.post(COMPANY["url"], json=page(PAGE_SIZE, 0, 5))
    mock_any_detail()

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert len(jobs) == total
    assert len(responses.calls) == 2 + total  # 2 list pages + 1 detail call/job
    post_bodies: list[WorkdayJobPostingsRequest] = [
        json.loads(cast(bytes, c.request.body))
        for c in responses.calls
        if c.request.method == "POST" and c.request.body is not None
    ]
    assert [b["offset"] for b in post_bodies] == [0, PAGE_SIZE]


@responses.activate
def test_expands_multi_location_postings_via_detail_endpoint() -> None:
    multi = posting(title="Multi", path="/job/X/Multi", loc="3 Locations", rid="M-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [multi]})
    responses.get(
        f"{DETAIL_BASE}/job/X/Multi",
        json={"jobPostingInfo": {
            "location": "Montreal, Canada",
            "additionalLocations": ["Toronto, Canada", "Remote"],
            "jobDescription": "<p>Multi-location role.</p>",
        }},
    )

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Montreal, Canada", "Toronto, Canada", "Remote"]
    assert jobs[0].location == "Montreal, Canada"
    assert jobs[0].description == "Multi-location role."


@responses.activate
def test_multi_location_falls_back_to_text_on_detail_failure() -> None:
    multi = posting(title="Multi", path="/job/X/Multi", loc="3 Locations", rid="M-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [multi]})
    responses.get(f"{DETAIL_BASE}/job/X/Multi", status=500)

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["3 Locations"]
    assert jobs[0].description == ""


@responses.activate
def test_fetches_description_for_single_location_postings() -> None:
    single = posting(title="Single", path="/job/X/Single", loc="Montreal, Canada", rid="S-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [single]})
    responses.get(
        f"{DETAIL_BASE}/job/X/Single",
        json={"jobPostingInfo": {"jobDescription": "<p>Single-location role.</p>"}},
    )

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    # Detail endpoint is now called even for single-location postings
    assert len(responses.calls) == 2  # 1 list + 1 detail
    assert jobs[0].locations == ["Montreal, Canada"]
    assert jobs[0].description == "Single-location role."


@responses.activate
def test_description_empty_on_detail_failure() -> None:
    single = posting(title="Single", path="/job/X/Single", loc="Montreal, Canada", rid="S-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [single]})
    responses.get(f"{DETAIL_BASE}/job/X/Single", status=500)

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    # Job is still created even though the detail fetch failed
    assert len(jobs) == 1
    assert jobs[0].description == ""
    assert jobs[0].locations == ["Montreal, Canada"]


@responses.activate
def test_skips_detail_fetch_for_job_already_in_previous_snapshot() -> None:
    single = posting(title="Single", path="/job/X/Single", loc="Montreal, Canada", rid="S-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [single]})
    # Deliberately no detail-endpoint mock registered — if the scraper tries
    # to call it, responses raises ConnectionError and the test fails.

    previous = {
        "cae:S-1": Job(
            id="cae:S-1", company="CAE", title="Single (old title)",
            location="Montreal, Canada", locations=["Montreal, Canada"],
            url="https://example.com/old", posted_on="Posted 3 Days Ago",
            source="workday", description="Cached description from last run.",
        )
    }

    jobs = WorkdayScraper(COMPANY, previous=previous).fetch_jobs()

    assert len(responses.calls) == 1  # list only — detail fetch was skipped
    assert jobs[0].description == "Cached description from last run."
    assert jobs[0].locations == ["Montreal, Canada"]
    # Fields that always come from this run's list response, never cached:
    assert jobs[0].title == "Single"
    assert jobs[0].posted_days == 0


@responses.activate
def test_fetches_detail_for_job_not_in_previous_snapshot() -> None:
    single = posting(title="Single", path="/job/X/Single", loc="Montreal, Canada", rid="S-1")
    responses.post(COMPANY["url"], json={"total": 1, "jobPostings": [single]})
    mock_any_detail({"jobPostingInfo": {"jobDescription": "<p>Freshly fetched.</p>"}})

    previous = {"cae:OTHER-JOB": Job(
        id="cae:OTHER-JOB", company="CAE", title="Unrelated", location="",
        url="https://example.com", posted_on="", source="workday",
    )}

    jobs = WorkdayScraper(COMPANY, previous=previous).fetch_jobs()

    assert len(responses.calls) == 2  # list + detail — not in previous, so fetched
    assert jobs[0].description == "Freshly fetched."


@responses.activate
def test_falls_back_to_external_path_when_no_bullet_fields() -> None:
    fixture: WorkdayJobPostingsResponse = {
        "total": 1,
        "jobPostings": [
            {
                "title": "No Bullets",
                "externalPath": "/job/Y/No-Bullets",
                "locationsText": "Remote",
                "postedOn": "Posted Today",
                "bulletFields": [],
            }
        ],
    }
    responses.post(COMPANY["url"], json=fixture)
    mock_any_detail()

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert jobs[0].id == "cae:/job/Y/No-Bullets"


@responses.activate
def test_skips_dangling_index_entries_with_no_title() -> None:
    """Real payload shape confirmed on Airbus's Workday tenant (2026-08): a
    posting with ONLY bulletFields present, every other field absent — a
    requisition still in the search index but whose own detail endpoint
    404s ("not found: Job_Posting_Anchor_ID=…"). Must be skipped before any
    detail fetch is attempted (there is nothing valid to fetch), not stored
    as a job with empty title/location/url.
    """
    fixture: WorkdayJobPostingsResponse = {
        "total": 2,
        "jobPostings": [
            {"bulletFields": ["JR10434331"]},  # dangling entry, no title
            posting(title="Real Job", path="/job/Z/Real-Job", rid="JR-2"),
        ],
    }
    responses.post(COMPANY["url"], json=fixture)
    mock_any_detail({"jobPostingInfo": {"jobDescription": "<p>Real work.</p>"}})

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert [j.title for j in jobs] == ["Real Job"]
    # Only one detail GET (for the real job) — the dangling entry never
    # reaches _fetch_detail at all.
    assert len(responses.calls) == 2  # list + one detail


@responses.activate
def test_skips_dangling_index_entry_even_with_whitespace_only_title() -> None:
    fixture: WorkdayJobPostingsResponse = {
        "total": 1,
        "jobPostings": [
            {"title": "   ", "bulletFields": ["JR10434331"]},
        ],
    }
    responses.post(COMPANY["url"], json=fixture)

    jobs = WorkdayScraper(COMPANY).fetch_jobs()

    assert jobs == []
    assert len(responses.calls) == 1  # list only — no detail fetch attempted
