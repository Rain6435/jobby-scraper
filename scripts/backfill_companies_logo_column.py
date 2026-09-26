"""One-off backfill: copy config.json's `logo` field into the `companies`
table's `logo` SQL column, without running a real scrape.

Bridges the gap between config.json (already has logos for 1,294 companies,
via `python -m scraper.backfill_logos`) and the `companies` table's `logo`
column, which only gets written by write_jobs() during a real scrape run
(scraper/main.py reads config.json's logo -> job.company_logo -> write_jobs()
persists it). Matches config.json entries to companies rows by exact name,
same key write_jobs() itself uses.

Usage:
    python -m scripts.backfill_companies_logo_column --database "sqlite:///../data/scraper.db"
    python -m scripts.backfill_companies_logo_column --database "sqlite:///../data/scraper.db" --dry-run
"""

import argparse
import json
import logging
from pathlib import Path

from sqlalchemy import text

from scraper.db import get_engine

log = logging.getLogger("scripts.backfill_companies_logo_column")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="SQLAlchemy database URL")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing"
    )
    args = parser.parse_args()

    with open(CONFIG_PATH) as f:
        config = json.load(f)
    logos_by_name = {c["name"]: c.get("logo", "") for c in config["companies"] if c.get("logo")}
    log.info(f"Loaded {len(logos_by_name)} companies with a logo from {CONFIG_PATH}")

    engine = get_engine(args.database)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, name, logo FROM companies")).fetchall()
        to_update = [
            (row.id, row.name, logos_by_name[row.name])
            for row in rows
            if row.name in logos_by_name and row.logo != logos_by_name[row.name]
        ]
        log.info(f"{len(rows)} companies in DB, {len(to_update)} need a logo update")

        if args.dry_run:
            for _id, name, logo in to_update[:20]:
                log.info(f"  would set {name!r} -> {logo}")
            if len(to_update) > 20:
                log.info(f"  ... and {len(to_update) - 20} more")
            return

        for company_id, _name, logo in to_update:
            conn.execute(
                text("UPDATE companies SET logo = :logo WHERE id = :id"),
                {"logo": logo, "id": company_id},
            )

    log.info(f"Updated {len(to_update)} companies' logo column")


if __name__ == "__main__":
    main()
