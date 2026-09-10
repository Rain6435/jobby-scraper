import json
from collections.abc import Mapping, Sequence

import responses

from scraper.boards.apple import (
    SEARCH_URL,
    AppleScraper,
)
from scraper.config_types import AppleConfig

COMPANY: AppleConfig = {"name": "Apple", "board": "apple"}


def _html_with_hydration(
    total: int = 1,
    jobs: Sequence[Mapping[str, object]] | None = None,
) -> str:
    if jobs is None:
        jobs = [
            {
                "positionId": "200314122",
                "postingTitle": "  Machine Learning Engineer  ",
                "transformedPostingTitle": "machine-learning-engineer",
                "jobSummary": "Design and build cutting-edge ML models.",
                "postDateInGMT": "2026-09-08T12:00:00.000Z",
                "locations": [
                    {
                        "name": "Cupertino, California, United States",
                        "city": "Cupertino",
                        "stateProvince": "California",
                        "countryName": "United States of America",
                    }
                ],
            }
        ]

    data: dict[str, object] = {
        "loaderData": {
            "search": {
                "totalRecords": total,
                "searchResults": jobs,
            }
        }
    }
    encoded = json.dumps(json.dumps(data))
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Search Jobs</title></head>
    <body>
    <script>
    window.__staticRouterHydrationData = JSON.parse({encoded});
    </script>
    </body>
    </html>
    """


@responses.activate
def test_maps_a_job_from_hydration() -> None:
    responses.get(SEARCH_URL, body=_html_with_hydration())

    jobs = AppleScraper(COMPANY).fetch_jobs()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "apple:200314122"
    assert j.company == "Apple"
    assert j.title == "Machine Learning Engineer"
    assert j.location == "Cupertino, California, United States"
    assert j.locations == ["Cupertino, California, United States"]
    assert j.url == "https://jobs.apple.com/en-us/details/200314122/machine-learning-engineer"
    assert j.source == "apple"
    assert j.description == "Design and build cutting-edge ML models."
    assert j.posted_days is not None


@responses.activate
def test_paginates_until_total_reached() -> None:
    j1 = {"positionId": "1", "postingTitle": "Job 1", "transformedPostingTitle": "job-1"}
    j2 = {"positionId": "2", "postingTitle": "Job 2", "transformedPostingTitle": "job-2"}
    cfg: AppleConfig = {"name": "Apple", "board": "apple"}

    responses.get(SEARCH_URL, body=_html_with_hydration(total=2, jobs=[j1]))
    responses.get(SEARCH_URL, body=_html_with_hydration(total=2, jobs=[j2]))

    jobs = AppleScraper(cfg).fetch_jobs()

    assert {j.id for j in jobs} == {"apple:1", "apple:2"}
    assert len(responses.calls) == 2


@responses.activate
def test_passes_filter_parameters() -> None:
    cfg: AppleConfig = {
        "name": "Apple",
        "board": "apple",
        "search": "compiler",
        "location": "united-states-USA",
    }
    responses.get(SEARCH_URL, body=_html_with_hydration())

    AppleScraper(cfg).fetch_jobs()

    url = responses.calls[0].request.url or ""
    assert "search=compiler" in url
    assert "location=united-states-USA" in url
