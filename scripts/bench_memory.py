#!/usr/bin/env python3
"""Peak/steady-state RSS of one full scraper.main.run(), offline.

No network: every company uses a fake board that returns deterministic
postings with ~5KB descriptions (roughly a real posting's size), and ~5% of
ids change between the seed run and the measured run so the diff, carryover
and write paths all do real work. The point is comparing two revisions of
this repo on the same machine, not predicting an exact production figure.

    python scripts/bench_memory.py --jobs 20000                  # unsharded
    python scripts/bench_memory.py --jobs 20000 --shard-size 50 --shard-job-target 5000
    SCRAPER_SQLITE_CACHE_KIB=8000 python scripts/bench_memory.py --jobs 20000

Each invocation seeds a throwaway SQLite database in a separate process
(so the seed run's allocations don't count), then runs once against it and
prints one JSON line: peak RSS (ru_maxrss), RSS after the run returns, and
wall time.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import main as main_module
from scraper.boards.base import BaseScraper
from scraper.models import Job

WORDS = (
    "python data engineer cloud kubernetes team build scale deliver requirements "
    "experience years degree benefits remote hybrid office customer platform "
    "design systems ownership collaborate mentor product quality security"
).split()
LOCATIONS = [
    "Remote",
    "Toronto, Ontario, Canada",
    "New York, NY",
    "San Francisco, CA",
    "Montreal, Quebec",
    "London, UK",
    "Austin, Texas",
    "Vancouver, BC",
]
COMPANIES = 200


def _description(job_id: str) -> str:
    rng = random.Random(job_id)
    return " ".join(rng.choice(WORDS) for _ in range(700))


def _jobs_for(company_idx: int, per_company: int, new_fraction: float) -> list[Job]:
    jobs: list[Job] = []
    for i in range(per_company):
        is_new = random.Random(f"new:{company_idx}:{i}").random() < new_fraction
        number = i + 10_000_000 if is_new else i
        job_id = f"company-{company_idx}:{number}"
        jobs.append(
            Job(
                id=job_id,
                company=f"Company {company_idx}",
                title=f"Engineer {i}",
                location=LOCATIONS[i % 8],
                url=f"https://example.com/{company_idx}/{number}",
                posted_on="",
                source="fake",
                locations=[LOCATIONS[i % 8], LOCATIONS[(i + 3) % 8]],
                posted_days=3,
                description=_description(job_id),
            )
        )
    return jobs


def _run(args: argparse.Namespace, seed: bool) -> dict[str, object]:
    per_company = args.jobs // COMPANIES
    new_fraction = 0.0 if seed else 0.05

    class FakeScraper(BaseScraper):
        source = "fake"

        def fetch_jobs(self) -> list[Job]:
            return _jobs_for(int(self.name.split()[-1]), per_company, new_fraction)

    config_path = Path(args.workdir) / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "companies": [
                    {"name": f"Company {i}", "board": "fake", "blurb": "", "logo": ""}
                    for i in range(COMPANIES)
                ]
            }
        )
    )
    deps = main_module.RunDeps(config_path=config_path, scrapers={"fake": FakeScraper})
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    logging.getLogger().setLevel(logging.WARNING)

    started = time.monotonic()
    code = main_module.run(
        database=f"sqlite:///{Path(args.workdir) / 'jobs.db'}",
        deps=deps,
        concurrency=args.concurrency,
        shard_size=None if seed else args.shard_size,
        shard_job_target=args.shard_job_target,
        per_company_timeout_s=None,
    )
    page = os.sysconf("SC_PAGE_SIZE")
    with open("/proc/self/statm") as f:
        resident_pages = int(f.read().split()[1])
    return {
        "exit": code,
        "jobs": args.jobs,
        "shard_size": args.shard_size,
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "end_rss_mb": round(resident_pages * page / 2**20, 1),
        "secs": round(time.monotonic() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--jobs", type=int, default=20_000)
    parser.add_argument("--shard-size", type=int)
    parser.add_argument(
        "--shard-job-target", type=int, default=main_module.DEFAULT_SHARD_JOB_TARGET
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--workdir", help=argparse.SUPPRESS)
    parser.add_argument("--seed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.workdir is None:
        with tempfile.TemporaryDirectory() as workdir:
            base = [sys.executable, __file__, *sys.argv[1:], "--workdir", workdir]
            subprocess.run([*base, "--seed"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(base, check=True)
        return

    result = _run(args, seed=args.seed)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
