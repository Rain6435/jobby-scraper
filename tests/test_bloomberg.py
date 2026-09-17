from __future__ import annotations

import responses
from requests import PreparedRequest

from scraper.boards.bloomberg import BloombergScraper
from scraper.config_types import BloombergConfig

SAMPLE_BLOOMBERG_HTML_PAGE_1 = """
<!DOCTYPE html>
<html>
<body>
<div class="results">
  <article class="article article--result" id="article--1">
    <div class="article__header">
      <div class="article__header__text">
        <h3 class="article__header__text__title title title--04">
          <a class="link" href="https://bloomberg.avature.net/careers/JobDetail/Senior-Software-Engineer-BQL/22151">
            Senior Software Engineer - BQL
          </a>
        </h3>
        <div class="article__header__text__subtitle">
          <span class="list-item-location">New York, New York, United States</span>
        </div>
      </div>
    </div>
  </article>
  <article class="article article--result" id="article--2">
    <div class="article__header">
      <div class="article__header__text">
        <h3 class="article__header__text__title title title--04">
          <a class="link" href="/careers/JobDetail/Data-Analyst/22152">
            Data Analyst
          </a>
        </h3>
        <div class="article__header__text__subtitle">
          <span class="list-item-location">London, United Kingdom</span>
        </div>
      </div>
    </div>
  </article>
</div>
</body>
</html>
"""

SAMPLE_BLOOMBERG_HTML_PAGE_2 = """
<!DOCTYPE html>
<html>
<body>
<div class="results">
  <article class="article article--result" id="article--3">
    <div class="article__header">
      <div class="article__header__text">
        <h3 class="article__header__text__title title title--04">
          <a class="link" href="https://bloomberg.avature.net/careers/JobDetail/Quantitative-Researcher/22153">
            Quantitative Researcher
          </a>
        </h3>
        <div class="article__header__text__subtitle">
          <span class="list-item-location">New York, New York, United States</span>
        </div>
      </div>
    </div>
  </article>
</div>
</body>
</html>
"""

SAMPLE_EMPTY_HTML = """
<!DOCTYPE html>
<html><body><div class="results"></div></body></html>
"""

SAMPLE_TWOSIGMA_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="results">
  <article class="article article--result" id="article--1">
    <div class="article__header">
      <div class="article__header__text">
        <h3 class="article__header__text__title title">
          <a class="link" href="https://careers.twosigma.com/careers/JobDetail/New-York-AI-Scientist/13671">
            AI Research Scientist - Campus
          </a>
        </h3>
        <div class="article__header__content">
          <div class="article__header__content__text">
            <span class="paragraph_inner-span">United States - NY New York</span>
          </div>
        </div>
      </div>
    </div>
  </article>
</div>
</body>
</html>
"""


@responses.activate
def test_fetch_jobs_success() -> None:
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=0",
        body=SAMPLE_BLOOMBERG_HTML_PAGE_1,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=2",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {"name": "Bloomberg", "board": "bloomberg"}
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2

    j1 = jobs[0]
    assert j1.id == "bloomberg:22151"
    assert j1.company == "Bloomberg"
    assert j1.title == "Senior Software Engineer - BQL"
    assert j1.location == "New York, New York, United States"
    assert j1.locations == ["New York, New York, United States"]
    assert (
        j1.url
        == "https://bloomberg.avature.net/careers/JobDetail/Senior-Software-Engineer-BQL/22151"
    )
    assert j1.source == "bloomberg"

    j2 = jobs[1]
    assert j2.id == "bloomberg:22152"
    assert j2.company == "Bloomberg"
    assert j2.title == "Data Analyst"
    assert j2.location == "London, United Kingdom"
    assert j2.url == "https://bloomberg.avature.net/careers/JobDetail/Data-Analyst/22152"


@responses.activate
def test_fetch_jobs_pagination() -> None:
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=0",
        body=SAMPLE_BLOOMBERG_HTML_PAGE_1,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=2",
        body=SAMPLE_BLOOMBERG_HTML_PAGE_2,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=3",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {"name": "Bloomberg", "board": "bloomberg", "max_pages": 5}
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 3
    assert jobs[2].id == "bloomberg:22153"
    assert jobs[2].title == "Quantitative Researcher"


@responses.activate
def test_fetch_jobs_custom_url_twosigma() -> None:
    responses.get(
        "https://careers.twosigma.com/careers/OpenRoles?jobOffset=0",
        body=SAMPLE_TWOSIGMA_HTML,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://careers.twosigma.com/careers/OpenRoles?jobOffset=1",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {
        "name": "Two Sigma",
        "board": "bloomberg",
        "url": "https://careers.twosigma.com/careers/OpenRoles",
    }
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "two-sigma:13671"
    assert j.company == "Two Sigma"
    assert j.title == "AI Research Scientist - Campus"
    assert j.location == "United States - NY New York"
    assert j.url == "https://careers.twosigma.com/careers/JobDetail/New-York-AI-Scientist/13671"


@responses.activate
def test_fetch_jobs_location_filter() -> None:
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=0",
        body=SAMPLE_BLOOMBERG_HTML_PAGE_1,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=2",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {
        "name": "Bloomberg",
        "board": "bloomberg",
        "location": "London",
    }
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Data Analyst"
    assert jobs[0].location == "London, United Kingdom"


@responses.activate
def test_fetch_jobs_query_endpoint() -> None:
    def callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        assert "/SearchJobs/engineer" in (request.url or "")
        return (200, {"Content-Type": "text/html"}, SAMPLE_BLOOMBERG_HTML_PAGE_1)

    responses.add_callback(
        responses.GET,
        "https://bloomberg.avature.net/careers/SearchJobs/engineer",
        callback=callback,
        content_type="text/html",
    )
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs/engineer?jobOffset=2",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {
        "name": "Bloomberg",
        "board": "bloomberg",
        "query": "engineer",
        "max_pages": 2,
    }
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()
    assert len(jobs) == 2


@responses.activate
def test_fetch_jobs_network_error() -> None:
    responses.get(
        "https://bloomberg.avature.net/careers/SearchJobs?jobOffset=0",
        status=500,
    )

    company: BloombergConfig = {"name": "Bloomberg", "board": "bloomberg"}
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()
    assert jobs == []


@responses.activate
def test_fetch_jobs_lululemon_style() -> None:
    html = """
    <div class="results">
      <article class="article article--result">
        <div class="article__header">
          <div class="article__header__text">
            <h3 class="article__header__text__title">
              <a href="https://careers.lululemon.com/en_US/careers/JobDetail/Guest-Experience-Lead/63919">
                Guest Experience Lead
              </a>
            </h3>
            <div class="article__header__text__subtitle">
              <span>Boston, Massachusetts, United States</span>
            </div>
          </div>
        </div>
      </article>
    </div>
    """
    responses.get(
        "https://careers.lululemon.com/en_US/careers/SearchJobs?jobOffset=0",
        body=html,
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://careers.lululemon.com/en_US/careers/SearchJobs?jobOffset=1",
        body=SAMPLE_EMPTY_HTML,
        status=200,
        content_type="text/html",
    )

    company: BloombergConfig = {
        "name": "Lululemon",
        "board": "bloomberg",
        "url": "https://careers.lululemon.com/en_US/careers/SearchJobs",
    }
    scraper = BloombergScraper(company)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "lululemon:63919"
    assert jobs[0].title == "Guest Experience Lead"
    assert jobs[0].location == "Boston, Massachusetts, United States"
