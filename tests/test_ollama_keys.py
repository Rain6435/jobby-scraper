import json
from pathlib import Path

import pytest

from scraper import ollama_keys


def test_parse_keys_splits_trims_drops_empty() -> None:
    assert ollama_keys.parse_keys("a, b ,, c") == ["a", "b", "c"]


def test_parse_keys_single_key_no_commas() -> None:
    assert ollama_keys.parse_keys("solo-key") == ["solo-key"]


def test_parse_keys_empty_string() -> None:
    assert ollama_keys.parse_keys("") == []


def test_is_hourly_limit_error_matches_marker() -> None:
    assert ollama_keys.is_hourly_limit_error(
        429, "you've reached your hourly usage limit, please wait or upgrade to continue"
    )


def test_is_hourly_limit_error_matches_session_limit_wording() -> None:
    """Observed live 2026-08-14: Ollama's actual 429 body used "session
    usage limit" wording, not "hourly usage limit" — kept in sync with the
    same test in the parent pipeline's tests/test_ollama_keys.py."""
    assert ollama_keys.is_hourly_limit_error(
        429,
        "you (schedulopro) have reached your session usage limit, "
        "upgrade for higher limits: https://ollama.com/upgrade",
    )


def test_is_hourly_limit_error_matches_weekly_limit_wording() -> None:
    """Observed live 2026-08-22: Ollama's actual 429 body used "weekly
    usage limit" wording, a third phrasing after "hourly" and "session" —
    kept in sync with the same test in the parent pipeline's
    tests/test_ollama_keys.py."""
    assert ollama_keys.is_hourly_limit_error(
        429,
        "you (schedulopro) have reached your weekly usage limit, "
        "upgrade for higher limits: https://ollama.com/upgrade",
    )


def test_is_hourly_limit_error_false_for_concurrency_429() -> None:
    assert not ollama_keys.is_hourly_limit_error(429, "too many concurrent requests")


def test_is_hourly_limit_error_false_for_non_429() -> None:
    assert not ollama_keys.is_hourly_limit_error(500, "hourly usage limit")


def test_is_concurrency_error_matches_marker() -> None:
    assert ollama_keys.is_concurrency_error(429, "too many concurrent requests")


def test_is_concurrency_error_false_for_hourly_limit() -> None:
    assert not ollama_keys.is_concurrency_error(429, "you've reached your hourly usage limit")


def test_usable_keys_all_usable_when_no_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(tmp_path / "state.json"))
    keys = ["k1", "k2", "k3"]
    assert ollama_keys.usable_keys(keys) == keys


def test_mark_exhausted_removes_key_from_usable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(tmp_path / "state.json"))
    keys = ["k1", "k2", "k3"]
    ollama_keys.mark_exhausted("k2")
    assert ollama_keys.usable_keys(keys) == ["k1", "k3"]


def test_mark_exhausted_persists_across_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(state_file))
    ollama_keys.mark_exhausted("k1")
    assert state_file.exists()
    # A fresh call (simulating a new process reading the same file) sees it too.
    assert ollama_keys.usable_keys(["k1", "k2"]) == ["k2"]


def test_exhausted_key_becomes_usable_again_after_cooldown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(tmp_path / "state.json"))
    now = 1_000_000.0
    ollama_keys.mark_exhausted("k1", now=now)
    # Still within the cooldown window.
    assert ollama_keys.usable_keys(["k1", "k2"], now=now + 60) == ["k2"]
    # Past the cooldown window.
    after = now + ollama_keys.EXHAUSTION_COOLDOWN_SECONDS + 1
    assert ollama_keys.usable_keys(["k1", "k2"], now=after) == ["k1", "k2"]


def test_all_keys_exhausted_returns_empty_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(tmp_path / "state.json"))
    ollama_keys.mark_exhausted("k1")
    ollama_keys.mark_exhausted("k2")
    assert ollama_keys.usable_keys(["k1", "k2"]) == []


def test_corrupt_state_file_treated_as_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("not valid json{{{", encoding="utf-8")
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(state_file))
    assert ollama_keys.usable_keys(["k1"]) == ["k1"]


def test_state_stores_key_id_not_raw_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    monkeypatch.setenv("OLLAMA_KEY_ROTATION_STATE_FILE", str(state_file))
    secret = "sk-super-secret-value"
    ollama_keys.mark_exhausted(secret)
    raw = state_file.read_text(encoding="utf-8")
    assert secret not in raw
    data = json.loads(raw)
    assert list(data.keys()) == [ollama_keys._key_id(secret)]


def test_default_state_path_uses_parent_data_dir_when_nested() -> None:
    # This repo IS nested inside job_pipeline/ in this environment, so the
    # real default should resolve to ../data/ollama_key_rotation.json.
    path = ollama_keys._default_state_path()
    assert path.name == "ollama_key_rotation.json"
    assert path.parent.name == "data"
