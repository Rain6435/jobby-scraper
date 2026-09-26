import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import responses

from scraper.link_parser import (
    JobParseError,
    job_to_dict,
    parse_job_url,
)
from scraper.models import Job


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    cfg_file = tmp_path / "config.json"
    data = {
        "companies": [
            {
                "name": "Ciena",
                "board": "workday",
                "url": "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/jobs",
                "careers_base": "https://ciena.wd5.myworkdayjobs.com/en-US/Careers",
            },
            {
                "name": "Behavox",
                "board": "greenhouse",
                "token": "behavox",
            },
            {
                "name": "MaintainX",
                "board": "ashby",
                "slug": "maintainx",
            },
            {
                "name": "Palantir Technologies",
                "board": "lever",
                "company": "palantir",
            },
            {
                "name": "Euna Solutions",
                "board": "bamboohr",
                "company": "euna",
            },
            {
                "name": "SmartCorp",
                "board": "smartrecruiters",
                "company": "smartcorp",
            },
            {
                "name": "Ayana",
                "board": "workable",
                "company": "ayana",
            },
            {
                "name": "Government of Canada",
                "board": "gc_jobs",
                "blurb": "Federal public service of Canada.",
            },
        ]
    }
    cfg_file.write_text(json.dumps(data), encoding="utf-8")
    return cfg_file


@responses.activate
def test_parse_workday(tmp_config: Path) -> None:
    url = "https://ciena.wd5.myworkdayjobs.com/en-US/Careers/job/Atlanta/Routing-Manager_R031594"
    cxs_url = "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/job/Atlanta/Routing-Manager_R031594"

    responses.get(
        cxs_url,
        json={
            "jobPostingInfo": {
                "title": "Routing Manager",
                "jobReqId": "R031594",
                "location": "Atlanta",
                "additionalLocations": ["Remote-US"],
                "postedOn": "Posted 5 Days Ago",
                "jobDescription": "<p>Lead the routing team.</p>",
                "externalPath": "/job/Atlanta/Routing-Manager_R031594",
            }
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "ciena:R031594"
    assert job.company == "Ciena"
    assert job.title == "Routing Manager"
    assert job.location == "Atlanta"
    assert job.locations == ["Atlanta", "Remote-US"]
    assert job.posted_days == 5
    assert job.source == "workday"
    assert job.description == "Lead the routing team."


@responses.activate
def test_parse_workday_details_path(tmp_config: Path) -> None:
    url = "https://ciena.wd5.myworkdayjobs.com/en-US/Careers/details/Routing-Manager_R031594"
    cxs_url = (
        "https://ciena.wd5.myworkdayjobs.com/wday/cxs/ciena/Careers/job/Routing-Manager_R031594"
    )

    responses.get(
        cxs_url,
        json={
            "jobPostingInfo": {
                "title": "Routing Manager",
                "jobReqId": "R031594",
                "location": "Atlanta",
                "postedOn": "Posted 5 Days Ago",
                "jobDescription": "<p>Lead the routing team.</p>",
                "externalPath": "/job/Routing-Manager_R031594",
            }
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "ciena:R031594"
    assert job.company == "Ciena"
    assert job.title == "Routing Manager"
    assert job.source == "workday"


@responses.activate
def test_parse_greenhouse(tmp_config: Path) -> None:
    url = "https://job-boards.greenhouse.io/behavox/jobs/8132548"
    api_url = "https://boards-api.greenhouse.io/v1/boards/behavox/jobs/8132548?questions=false"

    three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    responses.get(
        api_url,
        json={
            "id": 8132548,
            "title": "Account Executive",
            "first_published": three_days_ago,
            "location": {"name": "Milan, Italy"},
            "offices": [{"location": "Milan, Italy"}, {"location": "Rome, Italy"}],
            "content": "<div>Enterprise sales role.</div>",
            "absolute_url": url,
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "behavox:8132548"
    assert job.company == "Behavox"
    assert job.title == "Account Executive"
    assert job.location == "Milan, Italy"
    assert job.locations == ["Milan, Italy", "Rome, Italy"]
    assert job.posted_days == 3
    assert job.source == "greenhouse"
    assert job.description == "Enterprise sales role."


@responses.activate
def test_parse_greenhouse_embed(tmp_config: Path) -> None:
    url = "https://boards.greenhouse.io/embed/job_app?for=behavox&token=8132548"
    api_url = "https://boards-api.greenhouse.io/v1/boards/behavox/jobs/8132548?questions=false"

    responses.get(
        api_url,
        json={
            "id": 8132548,
            "title": "Account Executive",
            "location": {"name": "Remote"},
            "content": "Sales.",
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "behavox:8132548"
    assert job.company == "Behavox"
    assert job.title == "Account Executive"


@responses.activate
def test_parse_ashby(tmp_config: Path) -> None:
    url = "https://jobs.ashbyhq.com/maintainx/d1dfc7d0-226a-4206-9c4d-4f50753b1341"
    api_url = "https://api.ashbyhq.com/posting-api/job-board/maintainx?includeCompensation=true"

    responses.get(
        api_url,
        json={
            "jobs": [
                {
                    "id": "d1dfc7d0-226a-4206-9c4d-4f50753b1341",
                    "title": "Full-Stack Developer",
                    "location": "San Francisco",
                    "secondaryLocations": [{"location": "Remote"}],
                    "publishedAt": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                    "descriptionPlain": "Full-stack engineer building web applications.",
                    "jobUrl": url,
                }
            ]
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "maintainx:d1dfc7d0-226a-4206-9c4d-4f50753b1341"
    assert job.company == "MaintainX"
    assert job.title == "Full-Stack Developer"
    assert job.location == "San Francisco"
    assert job.locations == ["San Francisco", "Remote"]
    assert job.posted_days == 1
    assert job.source == "ashby"
    assert "Full-stack engineer" in job.description


@responses.activate
def test_parse_lever(tmp_config: Path) -> None:
    url = "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd"
    api_url = "https://api.lever.co/v0/postings/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd"

    ms_ago = int((datetime.now(UTC) - timedelta(days=4)).timestamp() * 1000)
    responses.get(
        api_url,
        json={
            "id": "6ed76ce8-4156-4b60-b120-403538bd66cd",
            "text": "Administrative Business Partner",
            "categories": {
                "location": "Singapore",
                "allLocations": ["Singapore", "Tokyo"],
            },
            "createdAt": ms_ago,
            "descriptionPlain": "Administrative support role.",
            "hostedUrl": url,
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "palantir-technologies:6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert job.company == "Palantir Technologies"
    assert job.title == "Administrative Business Partner"
    assert job.location == "Singapore"
    assert job.locations == ["Singapore", "Tokyo"]
    assert job.posted_days == 4
    assert job.source == "lever"


@responses.activate
def test_parse_smartrecruiters(tmp_config: Path) -> None:
    url = "https://jobs.smartrecruiters.com/smartcorp/12345-dev"
    api_url = "https://api.smartrecruiters.com/v1/companies/smartcorp/postings/12345"

    responses.get(
        api_url,
        json={
            "id": "12345",
            "name": "Backend Engineer",
            "releasedDate": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
            "location": {"fullLocation": "Austin, TX"},
            "jobAd": {"sections": {"jobDescription": {"text": "<p>Develop microservices.</p>"}}},
            "postingUrl": url,
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "smartcorp:12345"
    assert job.title == "Backend Engineer"
    assert job.location == "Austin, TX"
    assert job.posted_days == 2
    assert job.source == "smartrecruiters"
    assert job.description == "Develop microservices."


@responses.activate
def test_parse_bamboohr(tmp_config: Path) -> None:
    url = "https://euna.bamboohr.com/careers/688"
    api_url = "https://euna.bamboohr.com/careers/688/detail"

    responses.get(
        api_url,
        json={
            "result": {
                "jobOpening": {
                    "jobOpeningName": "Director of Engineering",
                    "location": {"city": "Toronto", "state": "ON"},
                    "datePosted": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
                    "description": "<p>Engineering leadership.</p>",
                    "jobOpeningShareUrl": url,
                }
            }
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "euna-solutions:688"
    assert job.company == "Euna Solutions"
    assert job.title == "Director of Engineering"
    assert job.location == "Toronto, ON"
    assert job.posted_days == 5
    assert job.source == "bamboohr"
    assert job.description == "Engineering leadership."


@responses.activate
def test_parse_workable(tmp_config: Path) -> None:
    url = "https://apply.workable.com/ayana/j/1C71542D00/"
    api_url = "https://apply.workable.com/api/v2/accounts/ayana/jobs/1C71542D00"

    responses.get(
        api_url,
        json={
            "shortcode": "1C71542D00",
            "title": "Reservations Agent",
            "published_on": "2026-09-20",
            "locations": [{"city": "Bali", "country": "Indonesia"}],
            "description": "<p>Handle bookings.</p>",
        },
    )

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "ayana:1C71542D00"
    assert job.company == "Ayana"
    assert job.title == "Reservations Agent"
    assert job.location == "Bali, Indonesia"
    assert job.source == "workable"


@responses.activate
def test_parse_generic_schema_org_json_ld(tmp_config: Path) -> None:
    url = "https://careers.example.com/job/senior-dev"
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Careers at Example</title>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Cloud Architect",
        "hiringOrganization": {
          "@type": "Organization",
          "name": "Cloud Corp"
        },
        "description": "<p>Build cloud solutions with Kubernetes and AWS.</p>",
        "datePosted": "2026-09-10",
        "jobLocation": {
          "@type": "Place",
          "address": {
            "addressLocality": "Seattle",
            "addressRegion": "WA",
            "addressCountry": "US"
          }
        },
        "identifier": {
          "@type": "PropertyValue",
          "value": "ARCH-990"
        }
      }
      </script>
    </head>
    <body><h1>Job Info</h1></body>
    </html>
    """

    responses.get(url, body=html, status=200, content_type="text/html")

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "cloud-corp:ARCH-990"
    assert job.company == "Cloud Corp"
    assert job.title == "Senior Cloud Architect"
    assert job.location == "Seattle, WA, US"
    assert job.source == "schema.org"
    assert "Build cloud solutions" in job.description


@responses.activate
def test_parse_generic_opengraph_fallback(tmp_config: Path) -> None:
    url = "https://careers.acmecorp.com/position/123"
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta property="og:title" content="DevOps Lead" />
      <meta property="og:site_name" content="Acme Global" />
      <meta property="og:description" content="Lead infrastructure automation across regions." />
    </head>
    <body><h1>DevOps Lead</h1></body>
    </html>
    """

    responses.get(url, body=html, status=200, content_type="text/html")

    job = parse_job_url(url, config_path=tmp_config)
    assert job.company == "Acme Global"
    assert job.title == "DevOps Lead"
    assert job.description == "Lead infrastructure automation across regions."
    assert job.source == "html"


@responses.activate
def test_redirect_to_ats(tmp_config: Path) -> None:
    short_url = "https://jobs.short.link/xyz"
    final_gh_url = "https://job-boards.greenhouse.io/behavox/jobs/8132548"
    api_url = "https://boards-api.greenhouse.io/v1/boards/behavox/jobs/8132548?questions=false"

    # Mock redirect from short_url to final_gh_url
    responses.get(
        short_url,
        status=302,
        headers={"Location": final_gh_url},
    )
    responses.get(
        final_gh_url,
        body="<html>redirected</html>",
        status=200,
    )
    responses.get(
        api_url,
        json={
            "id": 8132548,
            "title": "Account Executive",
            "location": {"name": "Milan, Italy"},
            "content": "Enterprise sales.",
        },
    )

    job = parse_job_url(short_url, config_path=tmp_config)
    assert job.id == "behavox:8132548"
    assert job.title == "Account Executive"
    assert job.source == "greenhouse"


def test_invalid_url_raises() -> None:
    with pytest.raises(ValueError):
        parse_job_url("   ")


@responses.activate
def test_unparseable_page_raises() -> None:
    url = "https://unknown.com/empty"
    responses.get(url, body="<html><body>No content here</body></html>", status=200)
    with pytest.raises(JobParseError):
        parse_job_url(url)


def test_job_to_dict() -> None:
    job = Job(
        id="test:1",
        company="Test Co",
        title="Software Engineer",
        location="Remote",
        locations=["Remote"],
        url="https://example.com/job/1",
        posted_on="today",
        posted_days=0,
        source="test",
        description="Write code.",
    )
    d = job_to_dict(job)
    assert d["id"] == "test:1"
    assert d["company"] == "Test Co"
    assert d["title"] == "Software Engineer"


@responses.activate
def test_parse_gc_jobs_direct_poster(tmp_config: Path) -> None:
    url = "https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page1800?poster=2462749&toggleLanguage=en"
    html = """
    <!DOCTYPE html>
    <html>
    <body>
    <main>
        <h1><span class="no-break-word">Operational Administrative Support Clerk</span></h1>
        <h2 class="pst-h2">Royal Canadian Mounted Police - Central Region</h2>
        <h3 class="pst-h3">Closing date: September 24, 2026</h3>
        <div class="well">
            <b>Location</b><br>
            Ottawa (Ontario)
        </div>
        <p>Perform administrative duties for RCMP detachments.</p>
    </main>
    </body>
    </html>
    """
    responses.get(url, body=html, status=200)

    job = parse_job_url(url, config_path=tmp_config)
    assert job.id == "government-of-canada:2462749"
    assert job.company == "Royal Canadian Mounted Police - Central Region"
    assert job.company_group == "Government of Canada"
    assert job.title == "Operational Administrative Support Clerk"
    assert job.location == "Ottawa (Ontario)"
    assert job.posted_on == "Closing: September 24, 2026"
    assert job.source == "gc_jobs"
    assert "Perform administrative duties" in job.description


@responses.activate
def test_parse_gc_jobs_transition_poster(tmp_config: Path) -> None:
    gc_url = "https://emploisfp-psjobs.cfp-psc.gc.ca/psrs-srfp/applicant/page1800?poster=2458497&toggleLanguage=en"
    transition_html = """
    <!DOCTYPE html>
    <html>
    <body>
    <main>
        <h1>You will leave the <abbr title='Government of Canada'>GC</abbr> Jobs Web site</h1>
        <p>The job opportunity you have selected requires the Public Service Commission (PSC) to transfer you to the hiring organization's Web site.</p>
        <p>Select the link below to be transferred from the PSC's GC Jobs Web site and be directed to the new Web site.</p>
        <p><a href="https://careers.cse-cst.gc.ca/en/careers/software-developer-various-levels-CA-248221-en/">Software Developer (Various Levels)</a></p>
    </main>
    </body>
    </html>
    """
    target_url = (
        "https://careers.cse-cst.gc.ca/en/careers/software-developer-various-levels-CA-248221-en/"
    )
    target_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Software Developer (Various Levels)</title>
        <meta property="og:description" content="Software Developer (Various Levels) - Communications Security Establishment Canada" />
    </head>
    <body>
        <main>
            <h1>Software Developer (Various Levels)</h1>
            <p>Design, build and test secure communications software at CSE Canada.</p>
        </main>
    </body>
    </html>
    """
    responses.get(gc_url, body=transition_html, status=200)
    responses.get(target_url, body=target_html, status=200)

    job = parse_job_url(gc_url, config_path=tmp_config)
    assert job.url == target_url
    assert job.title == "Software Developer (Various Levels)"
    assert job.company == "Communications Security Establishment Canada"
    assert job.company_group == "Government of Canada"
    assert "You will leave the" not in job.title
    assert "You will leave the" not in job.description


@responses.activate
def test_parse_generic_html_transition(tmp_config: Path) -> None:
    generic_url = "https://portal.example.gov/redirect?req=123"
    trans_html = """
    <!DOCTYPE html>
    <html>
    <body>
    <main>
        <h1>You will leave the portal</h1>
        <p>Redirecting to external application page:</p>
        <p><a href="https://careers.example.com/jobs/456">Senior Analyst</a></p>
    </main>
    </body>
    </html>
    """
    target_url = "https://careers.example.com/jobs/456"
    target_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Senior Analyst - Example Corp</title>
        <meta property="og:site_name" content="Example Corp" />
        <meta property="og:description" content="Lead analysis projects." />
    </head>
    <body>
        <h1>Senior Analyst</h1>
    </body>
    </html>
    """
    responses.get(generic_url, body=trans_html, status=200)
    responses.get(target_url, body=target_html, status=200)

    job = parse_job_url(generic_url, config_path=tmp_config)
    assert job.url == target_url
    assert job.title == "Senior Analyst - Example Corp"
    assert job.company == "Example Corp"
