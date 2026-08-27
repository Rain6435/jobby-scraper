from scraper.models import Job
from scraper.storage import diff


def job(jid: str, title: str = "T") -> Job:
    return Job(
        id=jid,
        company="X",
        title=title,
        location="Montreal",
        url="https://example.com",
        posted_on="Posted Today",
        source="workday",
    )


def test_diff_finds_only_new_jobs() -> None:
    previous = {"x:1": job("x:1")}
    current = [job("x:1"), job("x:2")]

    new = diff(previous, current)

    assert [j.id for j in new] == ["x:2"]
