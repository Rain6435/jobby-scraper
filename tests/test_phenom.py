import json

import responses

from scraper.boards.phenom import (
    PhenomScraper,
    extract_ddo,
    normalize_urls,
)
from scraper.config_types import PhenomConfig

COMPANY: PhenomConfig = {
    "name": "Bell Canada",
    "board": "phenom",
    "url": "https://jobs.bell.ca/ca/en",
}

SAMPLE_DDO = {
    "eagerLoadRefineSearch": {
        "totalHits": 2,
        "data": {
            "jobs": [
                {
                    "jobId": "427797",
                    "reqId": "427797",
                    "jobSeqNo": "BECACA427797EXTERNALENCA",
                    "title": "Technician Roles in Manitoba",
                    "location": "Russell, Manitoba",
                    "multi_location": ["Russell, Manitoba", "Brandon, Manitoba"],
                    "city": "Russell",
                    "state": "Manitoba",
                    "country": "Canada",
                    "category": "Field Services",
                    "postedDate": "2026-08-20T12:00:00.000+0000",
                    "descriptionTeaser": "Physical technician duties across rural Manitoba.",
                },
                {
                    "jobId": "431546",
                    "reqId": "431546",
                    "jobSeqNo": "BECACA431546EXTERNALENCA",
                    "title": "Senior Security Architect",
                    "location": "Montreal, Quebec",
                    "multi_location": ["Montreal, Quebec"],
                    "city": "Montreal",
                    "state": "Quebec",
                    "country": "Canada",
                    "category": "Cybersecurity",
                    "postedDate": "2026-08-28T14:30:00.000+0000",
                    "descriptionTeaser": "Lead security architecture design for enterprise clients.",
                },
            ]
        },
    }
}

SAMPLE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<script type="text/javascript">
  phApp.ddo = {json.dumps(SAMPLE_DDO)};
  phApp.pageId = "page13";
</script>
</head>
<body><h1>Jobs</h1></body>
</html>
"""

DETAIL_DDO = {
    "jobDetail": {
        "data": {
            "job": {
                "description": "<p>Full posting: <strong>Exciting Security Role</strong> in Montreal.</p>"
            }
        }
    }
}

DETAIL_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<script type="text/javascript">
  phApp.ddo = {json.dumps(DETAIL_DDO)};
  phApp.pageId = "jobDetail";
</script>
</head>
<body><h1>Job Detail</h1></body>
</html>
"""


def test_normalize_urls():
    p, s = normalize_urls("https://jobs.bell.ca/ca/en")
    assert p == "https://jobs.bell.ca/ca/en"
    assert s == "https://jobs.bell.ca/ca/en/search-results"

    p2, s2 = normalize_urls("https://jobs.bell.ca/ca/en/search-results")
    assert p2 == "https://jobs.bell.ca/ca/en"
    assert s2 == "https://jobs.bell.ca/ca/en/search-results"

    p3, s3 = normalize_urls("https://jobs.bell.ca/ca/en/")
    assert p3 == "https://jobs.bell.ca/ca/en"
    assert s3 == "https://jobs.bell.ca/ca/en/search-results"


def test_extract_ddo():
    assert extract_ddo("<html>No script</html>") is None
    assert extract_ddo("phApp.ddo = {invalid: json}; phApp") is None
    res = extract_ddo(SAMPLE_HTML)
    assert res is not None
    refine = res.get("eagerLoadRefineSearch")
    assert refine is not None
    assert refine.get("totalHits") == 2


@responses.activate
def test_fetch_jobs_basic():
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/search-results",
        body=SAMPLE_HTML,
        status=200,
    )

    scraper = PhenomScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2

    j1 = jobs[0]
    assert j1.id == "bell-canada:427797"
    assert j1.company == "Bell Canada"
    assert j1.title == "Technician Roles in Manitoba"
    assert j1.location == "Russell, Manitoba"
    assert j1.locations == ["Russell, Manitoba", "Brandon, Manitoba"]
    assert j1.url == "https://jobs.bell.ca/ca/en/job/427797"
    assert j1.source == "phenom"
    assert j1.posted_date == "2026-08-20"
    assert j1.posted_days is not None
    assert j1.description == "Physical technician duties across rural Manitoba."

    j2 = jobs[1]
    assert j2.id == "bell-canada:431546"
    assert j2.title == "Senior Security Architect"
    assert j2.location == "Montreal, Quebec"


@responses.activate
def test_fetch_jobs_pagination():
    page1_ddo = {
        "eagerLoadRefineSearch": {
            "totalHits": 15,
            "data": {
                "jobs": [
                    {
                        "jobId": f"job-{i}",
                        "title": f"Engineer {i}",
                        "location": "Toronto, ON",
                        "postedDate": "2026-08-01T00:00:00.000+0000",
                    }
                    for i in range(10)
                ]
            },
        }
    }
    page2_ddo = {
        "eagerLoadRefineSearch": {
            "totalHits": 15,
            "data": {
                "jobs": [
                    {
                        "jobId": f"job-{i}",
                        "title": f"Engineer {i}",
                        "location": "Toronto, ON",
                        "postedDate": "2026-08-01T00:00:00.000+0000",
                    }
                    for i in range(10, 15)
                ]
            },
        }
    }

    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/search-results",
        body=f"phApp.ddo = {json.dumps(page1_ddo)}; phApp",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/search-results?from=10&s=1",
        body=f"phApp.ddo = {json.dumps(page2_ddo)}; phApp",
        status=200,
    )

    scraper = PhenomScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 15
    assert jobs[0].id == "bell-canada:job-0"
    assert jobs[14].id == "bell-canada:job-14"


@responses.activate
def test_fetch_jobs_filtering():
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/search-results",
        body=SAMPLE_HTML,
        status=200,
    )

    # Filter by location (Quebec)
    cfg_loc: PhenomConfig = {
        "name": "Bell Canada",
        "board": "phenom",
        "url": "https://jobs.bell.ca/ca/en",
        "location": "Quebec",
    }
    jobs_loc = PhenomScraper(cfg_loc).fetch_jobs()
    assert len(jobs_loc) == 1
    assert jobs_loc[0].title == "Senior Security Architect"

    # Filter by keyword (Technician)
    cfg_kw: PhenomConfig = {
        "name": "Bell Canada",
        "board": "phenom",
        "url": "https://jobs.bell.ca/ca/en",
        "keyword": "Technician",
    }
    jobs_kw = PhenomScraper(cfg_kw).fetch_jobs()
    assert len(jobs_kw) == 1
    assert jobs_kw[0].title == "Technician Roles in Manitoba"

    # Filter by category (Cybersecurity)
    cfg_cat: PhenomConfig = {
        "name": "Bell Canada",
        "board": "phenom",
        "url": "https://jobs.bell.ca/ca/en",
        "category": "Cybersecurity",
    }
    jobs_cat = PhenomScraper(cfg_cat).fetch_jobs()
    assert len(jobs_cat) == 1
    assert jobs_cat[0].title == "Senior Security Architect"


@responses.activate
def test_fetch_jobs_with_details():
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/search-results",
        body=SAMPLE_HTML,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/job/427797",
        body=DETAIL_HTML,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://jobs.bell.ca/ca/en/job/431546",
        body=DETAIL_HTML,
        status=200,
    )

    cfg: PhenomConfig = {
        "name": "Bell Canada",
        "board": "phenom",
        "url": "https://jobs.bell.ca/ca/en",
        "fetch_details": True,
    }
    jobs = PhenomScraper(cfg).fetch_jobs()
    assert len(jobs) == 2
    assert "Exciting Security Role" in jobs[0].description
    assert "Exciting Security Role" in jobs[1].description
