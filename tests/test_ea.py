import responses
from requests import PreparedRequest

from scraper.boards.ea import (
    SEARCH_URL,
    EaScraper,
)
from scraper.config_types import EAConfig

COMPANY: EAConfig = {"name": "Electronic Arts", "board": "ea", "fetch_details": True}


def _mock_search_html(jobs: list[tuple[str, str, str]], total: int = 20) -> str:
    articles: list[str] = []
    for jid, title, loc in jobs:
        slug = title.replace(" ", "-")
        url = f"https://jobs.ea.com/en_US/careers/JobDetail/{slug}/{jid}"
        articles.append(f"""
        <article class="article article--result">
            <div class="article__header">
                <h3 class="article__header__text__title">
                    <a class="link link_result" href="{url}">{title}</a>
                </h3>
                <div class="article__header__text__subtitle">
                    <span class="list-item-location">{loc}</span>
                    <span class="list-item-id">Role ID {jid}</span>
                    <span class="list-item-workerType">Regular</span>
                    <span class="list-item-department">Engineering</span>
                </div>
            </div>
        </article>
        """)
    return f"""
    <html><body>
        <span aria-label="{total} results">1-20 of {total}</span>
        {"".join(articles)}
    </body></html>
    """


def _mock_detail_html(desc: str) -> str:
    return f"""
    <html><body>
        <div class="article__content__view__field__value">Short text</div>
        <div class="article__content__view__field__value">{desc}</div>
    </body></html>
    """


@responses.activate
def test_fetches_jobs_successfully():
    j1 = ("215930", "Gameplay Engineer", "Vancouver, Canada")
    j2 = ("215934", "Graphics Programmer", "Redwood City, CA")

    responses.add(responses.GET, SEARCH_URL, body=_mock_search_html([j1, j2], total=2), status=200)

    responses.add(
        responses.GET,
        "https://jobs.ea.com/en_US/careers/JobDetail/Gameplay-Engineer/215930",
        body=_mock_detail_html("<p>Build gameplay mechanics for Apex Legends.</p>"),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://jobs.ea.com/en_US/careers/JobDetail/Graphics-Programmer/215934",
        body=_mock_detail_html("<p>Next-gen Frostbite rendering pipelines.</p>"),
        status=200,
    )

    scraper = EaScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].id == "electronic-arts:215930"
    assert jobs[0].title == "Gameplay Engineer"
    assert jobs[0].company == "Electronic Arts"
    assert jobs[0].source == "ea"
    assert jobs[0].location == "Vancouver, Canada"
    assert jobs[0].locations == ["Vancouver, Canada"]
    assert jobs[0].url == "https://jobs.ea.com/en_US/careers/JobDetail/Gameplay-Engineer/215930"
    assert "Build gameplay mechanics for Apex Legends." in jobs[0].description

    assert jobs[1].id == "electronic-arts:215934"
    assert "Next-gen Frostbite rendering pipelines." in jobs[1].description


@responses.activate
def test_pagination():
    page1_jobs = [(f"10{i}", f"Role {i}", "Redwood City, CA") for i in range(20)]
    page2_jobs = [("201", "Lead Animator", "Stockholm, Sweden")]

    empty_headers: dict[str, str] = {}

    def request_callback(request: PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = str(request.url or "")
        if "jobOffset=0" in url or "jobOffset" not in url:
            return (200, empty_headers, _mock_search_html(page1_jobs, total=21))
        elif "jobOffset=20" in url:
            return (200, empty_headers, _mock_search_html(page2_jobs, total=21))
        return (200, empty_headers, _mock_search_html([], total=21))

    responses.add_callback(responses.GET, SEARCH_URL, callback=request_callback)

    for jid, title, _ in page1_jobs + page2_jobs:
        slug = title.replace(" ", "-")
        responses.add(
            responses.GET,
            f"https://jobs.ea.com/en_US/careers/JobDetail/{slug}/{jid}",
            body=_mock_detail_html(f"Job description for {jid}"),
            status=200,
        )

    scraper = EaScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 21
    assert jobs[0].id == "electronic-arts:100"
    assert jobs[20].id == "electronic-arts:201"


@responses.activate
def test_fetch_details_disabled():
    j = ("555", "Producer", "Orlando, FL")
    responses.add(responses.GET, SEARCH_URL, body=_mock_search_html([j], total=1), status=200)

    cfg: EAConfig = {"name": "Electronic Arts", "board": "ea", "fetch_details": False}
    scraper = EaScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].description == ""
    assert len(responses.calls) == 1


@responses.activate
def test_search_parameter():
    j = ("777", "AI Scientist", "Austin, TX")
    responses.add(responses.GET, SEARCH_URL, body=_mock_search_html([j], total=1), status=200)
    responses.add(
        responses.GET,
        "https://jobs.ea.com/en_US/careers/JobDetail/AI-Scientist/777",
        body=_mock_detail_html("AI description"),
        status=200,
    )

    cfg: EAConfig = {"name": "Electronic Arts", "board": "ea", "search": "scientist"}
    scraper = EaScraper(cfg)
    jobs = scraper.fetch_jobs()

    assert len(jobs) == 1
    assert "search=scientist" in str(responses.calls[0].request.url or "")


@responses.activate
def test_handles_empty_search():
    html = "<html><body><span aria-label='0 results'>0 of 0</span></body></html>"
    responses.add(responses.GET, SEARCH_URL, body=html, status=200)

    scraper = EaScraper(COMPANY)
    jobs = scraper.fetch_jobs()

    assert jobs == []
