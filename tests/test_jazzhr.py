import responses

from scraper.boards.jazzhr import JazzHrScraper
from scraper.config_types import JazzHrConfig

COMPANY: JazzHrConfig = {
    "name": "DesignStudio",
    "board": "jazzhr",
    "company": "designstudio",
}
API = "https://app.jazz.co/feeds/export/jobs/designstudio"


def xml_body(*jobs: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<jobs>\n' + "\n".join(jobs) + "\n</jobs>"
    ).encode("utf-8")


@responses.activate
def test_maps_jazzhr_jobs() -> None:
    body = xml_body("""
        <job>
            <id>456789</id>
            <title>Lead Brand Designer</title>
            <department>Design</department>
            <city>Austin</city>
            <state>TX</state>
            <country>US</country>
            <url>https://designstudio.applytojob.com/apply/456789/lead-brand-designer</url>
            <description><![CDATA[<p>Shape the <em>future</em> of design.</p>]]></description>
        </job>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = JazzHrScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "designstudio:456789"
    assert job.company == "DesignStudio"
    assert job.title == "Lead Brand Designer"
    assert job.location == "Austin, TX"
    assert job.locations == ["Austin, TX"]
    assert job.url == "https://designstudio.applytojob.com/apply/456789/lead-brand-designer"
    assert job.posted_days is None
    assert job.posted_on == ""
    assert job.source == "jazzhr"
    assert "Shape the future of design." in job.description


@responses.activate
def test_handles_international_locations_and_empty_fields() -> None:
    body = xml_body("""
        <job>
            <id>999</id>
            <title>Architect</title>
            <city>Toronto</city>
            <state>ON</state>
            <country>Canada</country>
            <url>https://designstudio.applytojob.com/apply/999/architect</url>
            <description></description>
        </job>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = JazzHrScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].location == "Toronto, ON, Canada"
    assert jobs[0].locations == ["Toronto, ON, Canada"]
    assert jobs[0].description == ""
