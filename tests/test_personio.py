from datetime import datetime, timedelta, timezone

import responses

from scraper.boards.personio import PersonioScraper

COMPANY = {"name": "Ottonova", "board": "personio", "company": "ottonova"}
API = "https://ottonova.jobs.personio.de/xml"


def xml_body(*positions: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<workzag-jobs>\n'
        + "\n".join(positions)
        + "\n</workzag-jobs>"
    ).encode("utf-8")


@responses.activate
def test_maps_jobs_with_dates_and_additional_offices():
    created = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    body = xml_body(f"""
        <position>
            <id>2656243</id>
            <name>  Senior Accountant  </name>
            <office>München</office>
            <additionalOffices>
                <office>Berlin</office>
            </additionalOffices>
            <createdAt>{created}</createdAt>
            <jobDescriptions>
                <jobDescription>
                    <name>DEIN TEAM</name>
                    <value><![CDATA[<p>Join our <b>team</b>.</p>]]></value>
                </jobDescription>
            </jobDescriptions>
        </position>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = PersonioScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "ottonova:2656243"
    assert job.title == "Senior Accountant"
    assert job.locations == ["München", "Berlin"]
    assert job.location == "München"
    assert job.url == "https://ottonova.jobs.personio.de/job/2656243"
    assert job.posted_days == 2
    assert job.posted_on == "2 days ago"
    assert job.source == "personio"
    assert "DEIN TEAM" in job.description
    assert "Join our team." in job.description


@responses.activate
def test_falls_back_when_no_additional_offices_or_date_or_description():
    body = xml_body("""
        <position>
            <id>1</id>
            <name>Dev</name>
            <office>Remote</office>
            <createdAt></createdAt>
        </position>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = PersonioScraper(COMPANY).fetch_jobs()

    assert jobs[0].locations == ["Remote"]
    assert jobs[0].posted_days is None
    assert jobs[0].posted_on == ""
    assert jobs[0].description == ""


@responses.activate
def test_decodes_non_ascii_correctly():
    body = xml_body("""
        <position>
            <id>2</id>
            <name>Ingénieur qualité</name>
            <office>Köln</office>
            <createdAt></createdAt>
        </position>
    """)
    responses.get(API, body=body, content_type="application/xml")

    jobs = PersonioScraper(COMPANY).fetch_jobs()

    assert jobs[0].title == "Ingénieur qualité"
    assert jobs[0].location == "Köln"
