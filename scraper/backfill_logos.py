"""Backfill tool: Resolve and save unified SVG logos for companies in config.json.

Usage:
    uv run python -m scraper.backfill_logos [--dry-run] [--force] [--company "Name"] [--workers 16]

--dry-run:  Print resolution results, write nothing to disk or config.json.
--force:    Re-resolve and overwrite logos even if already present.
--company:  Scope resolution to a single company name.
--workers:  Concurrency limit for network requests (default: 16).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import cast

from scraper.config_types import CompanyConfig, ConfigFile
from scraper.logos import LOGO_DIR, resolve_company_logo, slugify_company

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scraper.backfill_logos")


def run(
    dry_run: bool = False,
    force: bool = False,
    target_company: str | None = None,
    workers: int = 16,
) -> int:
    """Run logo resolution across companies in config.json."""
    if not CONFIG_PATH.exists():
        log.error("Config file not found at %s", CONFIG_PATH)
        return 1

    config_data: object = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config_data, dict):
        log.error("Invalid config.json format")
        return 1

    config_dict = cast(ConfigFile, config_data)
    companies: list[CompanyConfig] = config_dict["companies"]

    if target_company:
        targets = [c for c in companies if c["name"].lower() == target_company.lower()]
        if not targets:
            log.error("Company %r not found in %s", target_company, CONFIG_PATH)
            return 1
    else:
        targets = companies

    to_process: list[CompanyConfig] = []
    for c in targets:
        existing_logo = c.get("logo")
        file_exists = False
        if existing_logo:
            target_file = ROOT / existing_logo
            file_exists = target_file.exists() and target_file.stat().st_size > 0

        if force or not existing_logo or not file_exists:
            to_process.append(c)

    print(
        f"Processing {len(to_process)} of {len(targets)} companies (force={force}, dry_run={dry_run}, workers={workers})..."
    )
    if not to_process:
        print("All target companies already have verified SVG logos.")
        return 0

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    tier_counts: Counter[str] = Counter()

    def worker_task(company: CompanyConfig) -> tuple[CompanyConfig, str, str]:
        name = company["name"]
        slug = slugify_company(name)
        rel_path = f"data/logos/{slug}.svg"
        svg_content, tier = resolve_company_logo(company)
        if not dry_run:
            target_path = ROOT / rel_path
            target_path.write_text(svg_content, encoding="utf-8")
        return company, rel_path, tier

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker_task, c): c for c in to_process}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
            comp, rel_path, tier = fut.result()
            tier_counts[tier] += 1
            if not dry_run:
                comp["logo"] = rel_path
            if i % 50 == 0 or i == len(to_process):
                print(f"  [{i}/{len(to_process)}] processed...")

    print("\nResolution Breakdown by Tier:")
    for tier, count in sorted(tier_counts.items()):
        pct = (count / len(to_process)) * 100
        print(f"  - {tier:25}: {count:4} ({pct:5.1f}%)")

    if dry_run:
        print(f"\nDry run complete — would update {len(to_process)} companies.")
        return 0

    # Write updated config.json safely
    temp_path = CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(config_dict, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(CONFIG_PATH)
    print(f"\nSuccessfully wrote {len(to_process)} logos to {CONFIG_PATH} and {LOGO_DIR}!")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change, write nothing"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-resolve logos even if already present"
    )
    parser.add_argument("--company", help="scope to a specific company name")
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="number of concurrent worker threads (default: 16)",
    )
    args = parser.parse_args()
    sys.exit(
        run(
            dry_run=args.dry_run,
            force=args.force,
            target_company=args.company,
            workers=args.workers,
        )
    )


if __name__ == "__main__":
    main()
