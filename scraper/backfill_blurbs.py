"""One-time backfill: generate an AI company blurb for every company in
config.json that doesn't already have one, and write it back.

Usage:
    ANTHROPIC_API_KEY=... python -m scraper.backfill_blurbs [--dry-run] [--force]

ANTHROPIC_AUTH_TOKEN (e.g. a Claude Code OAuth token) works as an alternative
to ANTHROPIC_API_KEY. Either can also be set in a .env file in the repo root
instead of exporting it inline (see .env.example) — loaded automatically.

--dry-run: print what would change, write nothing.
--force:   regenerate blurbs even for companies that already have one.

This is NOT part of the hourly pipeline (scraper/main.py never imports this
module). Run manually once for the initial company list, and again whenever
new companies are added without a blurb (see CLAUDE.md "Adding Companies").
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from scraper.summarize import summarize_company

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def run(dry_run: bool = False, force: bool = False) -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    companies = config["companies"]

    missing = [c for c in companies if force or not c.get("blurb")]
    print(f"{len(missing)} of {len(companies)} companies need a blurb")

    changed = 0
    for company in missing:
        blurb = summarize_company(company["name"], company.get("careers_base", ""))
        if not blurb:
            print(f"  SKIP (AI call failed or no key): {company['name']}")
            continue
        print(f"  {company['name']}: {blurb}")
        if not dry_run:
            company["blurb"] = blurb
            changed += 1

    if dry_run:
        print(f"Dry run — would update {len(missing)} companies")
        return 0

    if changed:
        CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote {changed} blurbs to {CONFIG_PATH}")
    return 0


def main() -> None:
    load_dotenv()  # local .env is optional; ANTHROPIC_API_KEY/AUTH_TOKEN can also be exported directly
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change, write nothing"
    )
    parser.add_argument(
        "--force", action="store_true", help="regenerate blurbs even if already present"
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
