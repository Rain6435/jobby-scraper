---
name: expand-companies
description: Autonomous company and job board discovery workflow for Jobby-Scraper. Use when the user requests adding or finding new companies, expanding specific regions (e.g. Seattle, Austin, Europe, UK, APAC), researching ATS boards (Greenhouse, Ashby, Lever, BambooHR, SmartRecruiters, Workday, Rippling, Recruitee, Workable, Breezy, Personio, Teamtailor), or verifying and updating config.json.
---

# Board-Agnostic Company & Job Board Expansion Skill

This skill defines the autonomous discovery, multi-platform ATS detection, deduplication, live validation, and registration workflow for expanding `jobby-scraper` across any region, industry, or company list.

---

## 1. Supported ATS Platforms & Config Schemas

Every entry in `config.json` must strictly conform to [scraper/config_types.py](file:///home/brosi/job_pipeline/jobby-scraper/scraper/config_types.py). All ATS platforms are first-class citizens in `jobby-scraper`:

| Board | Required Config Key(s) | Public Endpoint Pattern | Config JSON Example |
| :--- | :--- | :--- | :--- |
| **Greenhouse** | `token` | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | `{"name": "Stripe", "board": "greenhouse", "token": "stripe"}` |
| **Ashby** | `slug` | `api.ashbyhq.com/posting-api/job-board/{slug}` | `{"name": "Linear", "board": "ashby", "slug": "linear"}` |
| **Lever** | `company` | `api.lever.co/v0/postings/{company}?mode=json` | `{"name": "Figma", "board": "lever", "company": "figma"}` |
| **BambooHR** | `company` | `{company}.bamboohr.com/careers/list` | `{"name": "Postman", "board": "bamboohr", "company": "postman"}` |
| **SmartRecruiters** | `company` | `api.smartrecruiters.com/v1/companies/{company}/postings` | `{"name": "Ubisoft", "board": "smartrecruiters", "company": "ubisoft"}` |
| **Workday** | `url`, `careers_base` | `...wd<N>.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | `{"name": "Target", "board": "workday", "url": "...", "careers_base": "..."}` |
| **Rippling** | `board_id` | `ats.rippling.com/api/v2/board/{board_id}/jobs` | `{"name": "Superhuman", "board": "rippling", "board_id": "superhuman"}` |
| **Recruitee** | `company` | `{company}.recruitee.com/api/offers` | `{"name": "Transloadit", "board": "recruitee", "company": "transloadit"}` |
| **Workable** | `company` | `apply.workable.com/api/v3/accounts/{company}/jobs` | `{"name": "Taxfix", "board": "workable", "company": "taxfix"}` |
| **Breezy** | `company` | `{company}.breezy.hr/json` | `{"name": "DuckDuckGo", "board": "breezy", "company": "duckduckgo"}` |
| **Personio** | `company` | `{company}.jobs.personio.de/xml` | `{"name": "Spryker", "board": "personio", "company": "spryker"}` |
| **Teamtailor** | `company` | `api.teamtailor.com/v1/jobs` | `{"name": "Kry", "board": "teamtailor", "company": "kry"}` |

---

## 2. Autonomous Expansion Runbook

When instructed to research or expand a geographic region, industry vertical, or specific company list:

### Step 1: Candidate Discovery & Identification
1. Identify high-priority employers in the target domain (tech unicorns, public enterprises, high-growth scaleups, research hubs, healthcare systems, utilities).
2. Look up or infer candidate career board identifiers (slugs, tokens, custom domains, or subdomains).

### Step 2: Multi-ATS Probing
Use [scripts/discover_companies.py](file:///home/brosi/job_pipeline/jobby-scraper/scripts/discover_companies.py) to probe all supported ATS platforms concurrently:

```bash
# Probe single company across all ATS engines
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name"

# Probe specific slug variations across all ATS engines
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name" --slug "name,name-ai,namehq"

# Batch probe a list of candidate companies
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --file candidate_companies.txt

# Automatically append verified entries into config.json and test
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name" --apply --test
```

### Step 3: Web Research for Custom/Complex Endpoints
For companies with custom career sites or unique endpoints:
1. Search the web for `"[Company Name]" ("greenhouse.io" OR "ashbyhq.com" OR "lever.co" OR "bamboohr.com" OR "smartrecruiters.com" OR "myworkdayjobs.com" OR "workable.com" OR "rippling.com")`.
2. Extract the canonical identifier or API endpoint.
3. Validate with `discover_companies.py` or by instantiating the board's scraper class directly.

### Step 4: Verification & Live Smoke Testing
1. **Deduplication**: Verify the company or endpoint signature does not already exist in `config.json`.
2. **Scraper Validation**: Execute a live smoke test to verify jobs parse cleanly:
   ```bash
   PYTHONPATH=. /usr/bin/python3 -m scraper.main --company "<Company Name>" --limit 1 --verbose
   ```
3. **Test Suite**: Run pytest to verify all board parsers and configurations pass:
   ```bash
   PYTHONPATH=. ../venv/bin/pytest tests/test_*.py
   ```

### Step 5: Presentation & Version Control
1. Present the discovered companies cleanly grouped by sector/industry with their active job counts and ATS engine.
2. Commit and push changes to `config.json` when requested.
