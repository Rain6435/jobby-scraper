#!/usr/bin/env python3
"""One-off maintenance: fix jobscraper_pool.country_code against already-
scraped data, without re-scraping or re-parsing (no LLM calls, no network
access — pure re-derivation/sync against data already on disk).

Two independent passes, each opt-in via its own flag:

--backfill-null
    Re-run resolve_country_from_location() (scraper/location_resolver.py)
    against every jobscraper_pool row whose country_code is still NULL. Only
    ever fills a gap — never touches an already-set value. Exists because
    country_code is set once, at scrape-insert time, into the canonical
    `locations` table (see scraper/location_resolver.py's
    get_or_create_locations) and is never revisited afterward; a resolver
    fix (new dot/dash-delimited shapes, the bare-city-name gazetteer table,
    etc.) only benefits newly-scraped jobs unless this is run.

--fix-mismatches
    Sync jobscraper_pool.country_code to the canonical `locations` table's
    own country_code wherever they disagree. Exists because a small number
    of jobscraper_pool rows were found (2026-09-01, prod) holding a stale
    country_code that no longer matches locations.country_code for the same
    location name — e.g. "Toronto, Ontario" stored as "US", "United States"
    stored as "CA" — evidently written under an old resolver version, never
    refreshed since. locations.name is the trusted, unique source of truth
    (confirmed unique — no ambiguous join risk); jobscraper_pool.location is
    a plain denormalized copy of it. Only ever overwrites a jobscraper_pool
    value that provably disagrees with the canonical table for the exact
    same location string — never invents a value from nothing (that's
    --backfill-null's job).

--sync-town-id
    Copy jobscraper_pool.town_id from the canonical `locations` table
    wherever jobscraper_pool's copy is still NULL and locations has a real
    value (locations.town_id is only ever populated by the separate
    scripts/backfill_town_ids.py run, never re-derived here). Same
    denormalized-copy relationship as country_code, and the same reason it
    goes stale: jobscraper_pool.town_id is set once at ingest time from
    whatever locations.town_id held then, and never revisited.

None of these passes touch `locations` itself, any other jobscraper_pool
column, or re-parse/re-score anything downstream. Safe to re-run: each pass
is idempotent (an already-correct row simply doesn't match its WHERE clause
on a second run).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.location_resolver import resolve_country_from_location


def backfill_null(conn: sqlite3.Connection) -> int:
    # Deliberately NOT scoped to parse_status = 'parsed' — country_code is a
    # location-resolution concern, set at ingest time, entirely independent
    # of whether a row has been through the separate LLM job-requirements
    # parse (parse_status). Restricting to 'parsed' here silently skipped
    # every 'pending'/'parse_failed' row — the majority of NULL rows in
    # practice — even though resolve_country_from_location() only needs
    # `location`, which every ingested row already has regardless of
    # parse_status.
    rows = conn.execute(
        "SELECT id, location FROM jobscraper_pool WHERE country_code IS NULL"
    ).fetchall()

    updated = 0
    for pool_id, location in rows:
        code = resolve_country_from_location(location)
        if code:
            conn.execute(
                "UPDATE jobscraper_pool SET country_code = ? WHERE id = ?",
                (code, pool_id),
            )
            updated += 1
    return updated


def fix_mismatches(conn: sqlite3.Connection) -> int:
    return conn.execute(
        """UPDATE jobscraper_pool
           SET country_code = (
               SELECT l.country_code FROM locations l WHERE l.name = jobscraper_pool.location
           )
           WHERE id IN (
               SELECT p.id FROM jobscraper_pool p
               JOIN locations l ON l.name = p.location
               WHERE p.country_code IS NOT NULL AND p.country_code != l.country_code
           )"""
    ).rowcount


def sync_town_id(conn: sqlite3.Connection) -> int:
    return conn.execute(
        """UPDATE jobscraper_pool
           SET town_id = (
               SELECT l.town_id FROM locations l WHERE l.name = jobscraper_pool.location
           )
           WHERE id IN (
               SELECT p.id FROM jobscraper_pool p
               JOIN locations l ON l.name = p.location
               WHERE p.town_id IS NULL AND l.town_id IS NOT NULL
           )"""
    ).rowcount


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--database", required=True, help="Path to the shared SQLite database (e.g. ../data/app.db)"
    )
    parser.add_argument(
        "--backfill-null", action="store_true", help="Fill country_code where it's currently NULL"
    )
    parser.add_argument(
        "--fix-mismatches",
        action="store_true",
        help="Correct country_code where it disagrees with the canonical locations table",
    )
    parser.add_argument(
        "--sync-town-id",
        action="store_true",
        help="Fill town_id from the canonical locations table where jobscraper_pool's copy is NULL",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = parser.parse_args()

    if not args.backfill_null and not args.fix_mismatches and not args.sync_town_id:
        parser.error("pass at least one of --backfill-null / --fix-mismatches / --sync-town-id")

    db_path = Path(args.database)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        if args.backfill_null:
            if args.dry_run:
                n = conn.execute(
                    "SELECT COUNT(*) FROM jobscraper_pool WHERE country_code IS NULL"
                ).fetchone()[0]
                print(f"[dry-run] --backfill-null would check {n} NULL rows")
            else:
                updated = backfill_null(conn)
                conn.commit()
                print(f"--backfill-null: filled country_code on {updated} rows")

        if args.fix_mismatches:
            if args.dry_run:
                n = conn.execute(
                    """SELECT COUNT(*) FROM jobscraper_pool p
                       JOIN locations l ON l.name = p.location
                       WHERE p.country_code IS NOT NULL AND p.country_code != l.country_code"""
                ).fetchone()[0]
                print(f"[dry-run] --fix-mismatches would correct {n} rows")
            else:
                corrected = fix_mismatches(conn)
                conn.commit()
                print(f"--fix-mismatches: corrected {corrected} rows")

        if args.sync_town_id:
            if args.dry_run:
                n = conn.execute(
                    """SELECT COUNT(*) FROM jobscraper_pool p
                       JOIN locations l ON l.name = p.location
                       WHERE p.town_id IS NULL AND l.town_id IS NOT NULL"""
                ).fetchone()[0]
                print(f"[dry-run] --sync-town-id would fill {n} rows")
            else:
                synced = sync_town_id(conn)
                conn.commit()
                print(f"--sync-town-id: filled town_id on {synced} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
