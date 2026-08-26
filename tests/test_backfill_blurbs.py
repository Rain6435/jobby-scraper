import json
from unittest.mock import patch

import scraper.backfill_blurbs as backfill_module


def write_config(path, companies):
    path.write_text(json.dumps({"companies": companies}), encoding="utf-8")


def test_writes_blurbs_for_companies_missing_one(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    write_config(config_path, [
        {"name": "Acme"}, {"name": "Beta", "blurb": "Already has one."},
    ])
    monkeypatch.setattr(backfill_module, "CONFIG_PATH", config_path)

    with patch.object(backfill_module, "summarize_company", return_value="Makes widgets."):
        result = backfill_module.run()

    assert result == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    blurbs = {c["name"]: c["blurb"] for c in data["companies"]}
    assert blurbs == {"Acme": "Makes widgets.", "Beta": "Already has one."}


def test_skips_companies_with_existing_blurb_unless_forced(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    write_config(config_path, [{"name": "Beta", "blurb": "Old blurb."}])
    monkeypatch.setattr(backfill_module, "CONFIG_PATH", config_path)

    with patch.object(backfill_module, "summarize_company", return_value="New blurb.") as mock_fn:
        backfill_module.run()
        mock_fn.assert_not_called()

        backfill_module.run(force=True)
        mock_fn.assert_called_once()

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["companies"][0]["blurb"] == "New blurb."


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    write_config(config_path, [{"name": "Acme"}])
    original_mtime = config_path.stat().st_mtime
    monkeypatch.setattr(backfill_module, "CONFIG_PATH", config_path)

    with patch.object(backfill_module, "summarize_company", return_value="Makes widgets."):
        backfill_module.run(dry_run=True)

    assert config_path.stat().st_mtime == original_mtime
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "blurb" not in data["companies"][0]


def test_failed_summarizer_call_leaves_company_without_blurb(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    write_config(config_path, [{"name": "Acme"}, {"name": "Beta"}])
    monkeypatch.setattr(backfill_module, "CONFIG_PATH", config_path)

    with patch.object(backfill_module, "summarize_company", return_value=""):
        result = backfill_module.run()

    assert result == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert all("blurb" not in c for c in data["companies"])
