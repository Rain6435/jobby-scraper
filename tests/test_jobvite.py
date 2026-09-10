from datetime import UTC, datetime, timedelta

import responses

from scraper.boards.jobvite import JobviteScraper
from scraper.config_types import JobviteConfig

COMPANY: JobviteConfig = {
    "name": "Zillow",
    "board": "jobvite",
    "company_id": "q9x9Vfws",
}
API = "https://app.jobvite.com/CompanyJobs/Xml.aspx?c=q9x9Vfws"


def xml_body(*jobs: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<result>\n' + "\n".join(jobs) + "\n</result>"
    ).encode("utf-8")


@responses.activate
def test_maps_jobvite_jobs_with_dates_and_locations() -> None:
    created_dt = datetime.now(UTC) - timedelta(days=5)
    date_str = created_dt.strftime("%m/%d/%Y")
    body = xml_body(f"""
        <job>
            <id>oF9vbfwR</id>
            <title>Principal Data Scientist</title>
            <date>{date_str}</date>
            <location>Seattle, WA</location>
            <detail-url>https://jobs.jobvite.com/zillow/job/oF9vbfwR</detail-url>
            <description><![CDATA[<p>Build ML <b>models</b> at scale.</p>]]></description>
        </job>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = JobviteScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "zillow:oF9vbfwR"
    assert job.company == "Zillow"
    assert job.title == "Principal Data Scientist"
    assert job.url == "https://jobs.jobvite.com/zillow/job/oF9vbfwR"
    assert job.location == "Seattle, WA"
    assert job.locations == ["Seattle, WA"]
    assert job.posted_days == 5
    assert job.posted_on == "5 days ago"
    assert job.source == "jobvite"
    assert "Build ML models at scale." in job.description


@responses.activate
def test_handles_multiline_locations_and_missing_date() -> None:
    body = xml_body("""
        <job>
            <requisition-id>REQ-101</requisition-id>
            <title>Account Executive</title>
            <date></date>
            <location>New York, NY; San Francisco, CA</location>
            <detail-url>https://jobs.jobvite.com/zillow/job/REQ-101</detail-url>
            <description>Sales role</description>
        </job>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = JobviteScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "zillow:REQ-101"
    assert jobs[0].locations == ["New York, NY", "San Francisco, CA"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
