from scraper.boards.wp_job_manager import parse_wp_job_manager_feed

_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:job_listing="https://example.com"
>
<channel>
<item>
	<title>Exhibits &amp; Collection Interpreter</title>
	<link>https://example.com/job/exhibits-collection-interpreter/</link>
	<pubDate>Sun, 23 Aug 2026 12:00:00 +0000</pubDate>
	<guid isPermaLink="false">https://example.com/?post_type=job_listing&#038;p=100</guid>
	<content:encoded><![CDATA[<p>Full <b>description</b> here.</p>]]></content:encoded>
	<job_listing:company><![CDATA[London Children's Museum]]></job_listing:company>
	<job_listing:location><![CDATA[London, ON]]></job_listing:location>
</item>
<item>
	<title>No Company Field</title>
	<link>https://example.com/job/no-company-field/</link>
	<pubDate>Sun, 23 Aug 2026 12:00:00 +0000</pubDate>
	<guid isPermaLink="false">https://example.com/?post_type=job_listing&#038;p=101</guid>
	<content:encoded><![CDATA[<p>No company element present.</p>]]></content:encoded>
</item>
<item>
	<title>Missing Guid Id</title>
	<link>https://example.com/job/missing-guid/</link>
	<guid isPermaLink="false">https://example.com/malformed</guid>
</item>
</channel>
</rss>
"""


def test_parses_title_entities_company_location_and_description():
    jobs = parse_wp_job_manager_feed(_FEED_XML, "test_board", "test-board", "Test Board")

    assert len(jobs) == 2  # third item has no p=<id> guid, skipped
    job = jobs[0]
    assert job.id == "test-board:100"
    assert job.title == "Exhibits & Collection Interpreter"
    assert job.company == "London Children's Museum"
    assert job.location == "London, ON"
    assert job.url == "https://example.com/job/exhibits-collection-interpreter/"
    assert job.source == "test_board"
    assert job.description == "Full description here."
    assert job.posted_days is not None


def test_falls_back_to_default_company_when_missing():
    jobs = parse_wp_job_manager_feed(_FEED_XML, "test_board", "test-board", "Test Board")

    assert jobs[1].company == "Test Board"
