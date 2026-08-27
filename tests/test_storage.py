import json
from pathlib import Path

from scraper.models import Job
from scraper.storage import diff, load_snapshot, save_snapshot


def job(jid: str, title: str = "T") -> Job:
    return Job(
        id=jid, company="X", title=title, location="Montreal",
        url="https://example.com", posted_on="Posted Today", source="workday",
    )


def test_load_snapshot_missing_file_is_first_run(tmp_path: Path) -> None:
    assert load_snapshot(tmp_path / "jobs.json") == {}


def test_load_snapshot_corrupt_file_is_first_run(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("\n", encoding="utf-8")  # the exact bytes that broke CI
    assert load_snapshot(path) == {}


def test_load_snapshot_tolerates_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    payload = '{"updated_at": "x", "jobs": []}'
    path.write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))
    assert load_snapshot(path) == {}


def test_diff_finds_only_new_jobs() -> None:
    previous = {"x:1": job("x:1")}
    current = [job("x:1"), job("x:2")]

    new = diff(previous, current)

    assert [j.id for j in new] == ["x:2"]


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    jobs = [job("x:1"), job("x:2")]

    save_snapshot(path, jobs, new_ids={"x:2"})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["updated_at"]
    flags = {j["id"]: j["is_new"] for j in data["jobs"]}
    assert flags == {"x:1": False, "x:2": True}

    reloaded = load_snapshot(path)
    assert set(reloaded) == {"x:1", "x:2"}
    assert reloaded["x:1"].first_seen  # stamped on save


def test_first_seen_preserved_on_resave(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    j = job("x:1")
    j.first_seen = "2026-01-01T00:00:00+00:00"

    save_snapshot(path, [j], new_ids=set())

    assert load_snapshot(path)["x:1"].first_seen == "2026-01-01T00:00:00+00:00"


def test_description_summary_and_blurb_survive_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    j = job("x:1")
    j.description = "Full posting text."
    j.role_summary = "Builds features."
    j.company_blurb = "Makes widgets."

    save_snapshot(path, [j], new_ids=set())
    reloaded = load_snapshot(path)

    assert reloaded["x:1"].description == "Full posting text."
    assert reloaded["x:1"].role_summary == "Builds features."
    assert reloaded["x:1"].company_blurb == "Makes widgets."
