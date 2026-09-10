from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import responses

from scraper.boards.governmentjobs import GovernmentJobsScraper
from scraper.config_types import GovernmentJobsConfig

COMPANY: GovernmentJobsConfig = {
    "name": "City of Seattle",
    "board": "governmentjobs",
    "agency": "seattle",
}
API = "https://agency.governmentjobs.com/jobfeed_v2.cfm?agency=seattle"


def rss_body(*items: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n<channel>\n'
        + "\n".join(items)
        + "\n</channel>\n</rss>"
    ).encode("utf-8")


@responses.activate
def test_maps_governmentjobs_with_pubdate_and_location() -> None:
    pub_dt = datetime.now(UTC) - timedelta(days=4)
    pub_str = format_datetime(pub_dt)
    body = rss_body(f"""
        <item>
            <title>Civil Engineer Principal</title>
            <link>https://www.governmentjobs.com/careers/seattle/jobs/4201010/civil-engineer-principal</link>
            <guid>https://www.governmentjobs.com/careers/seattle/jobs/4201010/civil-engineer-principal</guid>
            <pubDate>{pub_str}</pubDate>
            <job:location>Seattle, WA</job:location>
            <description><![CDATA[<p>Manage major civil <b>infrastructure</b> projects.</p>]]></description>
        </item>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = GovernmentJobsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "city-of-seattle:4201010"
    assert job.company == "City of Seattle"
    assert job.title == "Civil Engineer Principal"
    assert (
        job.url
        == "https://www.governmentjobs.com/careers/seattle/jobs/4201010/civil-engineer-principal"
    )
    assert job.location == "Seattle, WA"
    assert job.locations == ["Seattle, WA"]
    assert job.posted_days == 4
    assert job.posted_on == "4 days ago"
    assert job.source == "governmentjobs"
    assert "Manage major civil infrastructure projects." in job.description


@responses.activate
def test_extracts_id_from_jobid_param_and_handles_missing_fields() -> None:
    body = rss_body("""
        <item>
            <title>Administrative Specialist</title>
            <link>https://www.governmentjobs.com/careers/seattle?jobId=887766</link>
            <guid>887766</guid>
            <description>Admin support</description>
        </item>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = GovernmentJobsScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "city-of-seattle:887766"
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].locations == []
