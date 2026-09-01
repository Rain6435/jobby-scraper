---
name: expand-companies
description: Autonomous company and job board discovery workflow for Jobby-Scraper. Use when the user requests adding or finding new companies, expanding specific regions (e.g. Seattle, Austin, Europe, UK, APAC), researching ATS boards (Workday, Greenhouse, Ashby, Lever, BambooHR, SmartRecruiters, Rippling, Recruitee, Workable), or verifying and updating config.json.
---

# Expand Companies & Job Boards Skill

This skill guides the autonomous discovery, multi-ATS probing, deduplication, verification, and registration of company career boards for `jobby-scraper`.

## 1. Automated Discovery Workflow

When asked to expand companies for a region, industry, or candidate list:

### Step 1: Candidate Generation
Identify target employer candidates for the specified region or sector (e.g., tech unicorns, publicly traded enterprises, high-growth startups, research institutions, regional utilities, healthcare networks).

### Step 2: Use the Discovery Script
Run `scripts/discover_companies.py` to probe ATS platforms concurrently:

```bash
# Single company or comma-separated candidate slugs
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name" --slug "candidate-slug,candidateslug"

# Batch probe from a list or file
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --file candidate_list.txt

# Automatically append verified entries into config.json and run tests
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name" --apply --test
```

### Step 3: Workday Endpoint Probing
For large enterprises on Workday:
- Find the `wday/cxs` endpoint format:
  `https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<career_site>/jobs`
- Verify with `discover_companies.py`:
  ```bash
  PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py \
    --company "<Company Name>" \
    --workday-url "https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs" \
    --workday-base "https://<tenant>.wd<N>.myworkdayjobs.com/en-US/<site>" \
    --apply --test
  ```

### Step 4: Verification & Smoke Testing
1. Ensure all entries in `config.json` conform strictly to [scraper/config_types.py](file:///home/brosi/job_pipeline/jobby-scraper/scraper/config_types.py).
2. Smoke test scraping for one or more additions:
   ```bash
   PYTHONPATH=. /usr/bin/python3 -m scraper.main --company "<Company Name>" --limit 1 --verbose
   ```
3. Run test suite:
   ```bash
   PYTHONPATH=. ../venv/bin/pytest tests/test_workday.py tests/test_greenhouse.py tests/test_lever.py tests/test_ashby.py tests/test_bamboohr.py tests/test_smartrecruiters.py
   ```

### Step 5: Git Commit & Push (When Requested)
Commit changes to `config.json` with a clear message and push to `origin/main`.
