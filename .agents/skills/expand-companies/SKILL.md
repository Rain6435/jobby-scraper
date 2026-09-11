---
name: expand-companies
description: Autonomous cross-industry company and job board discovery workflow for Jobby-Scraper. Use when the user requests adding or finding new companies, expanding specific regions (e.g. Seattle, Austin, Europe, UK, APAC), researching ATS boards (Greenhouse, Ashby, Lever, BambooHR, SmartRecruiters, Workday, Rippling, Recruitee, Workable, Breezy, Personio, Teamtailor), or verifying and updating config.json.
---

# Cross-Industry Job Board Expansion Skill

This skill defines the autonomous discovery, multi-ATS platform detection, deduplication, live validation, and registration workflow for expanding `jobby-scraper` across **all industry sectors and employment fields**.

To serve the widest range of job seekers, company discovery must never be restricted to tech startups or software engineering alone. Every regional or thematic expansion must actively seek out and cover diverse employment fields.

---

## 1. Multi-Field Industry Coverage Matrix

When expanding any geographic region, metropolitan area, or thematic target, the discovery process must survey employers across these core fields:

| Industry Sector | Representative Employer Types | Common Roles / Profiles Served |
| :--- | :--- | :--- |
| **Healthcare, Hospitals & Clinical Systems** | Hospital networks, regional health authorities, medical centers, academic clinics, outpatient networks, blood banks | Nurses, physicians, clinical coordinators, technicians, healthcare administrators, therapists |
| **Biotech, Pharma, Life Sciences & Genomics** | Drug discovery platforms, genomics laboratories, CROs, medical device manufacturers, therapeutic research hubs | Research scientists, lab technicians, bioinformaticians, regulatory affairs, QA/QC specialists |
| **Higher Education, Universities & Research** | Public & private research universities, community colleges, vocational polytechnics, independent research institutes | Faculty, academic advisors, researchers, lab managers, admissions officers, campus operations |
| **Public Sector, Municipal & Transit Agencies** | City/county administrations, regional transit authorities, public housing agencies, port authorities, airport operators | Urban planners, civil inspectors, transit operators, policy analysts, public administrators |
| **Utilities, Energy, CleanTech & Environment** | Electric, water, and gas utilities, district heating/cooling networks, renewable energy developers, nuclear/fusion innovators, environmental consultancies | Power engineers, grid operators, environmental scientists, field technicians, safety managers |
| **Financial Services, Banking & Insurance** | Commercial banks, credit unions, wealth management firms, insurance carriers, pension boards, fintechs | Financial analysts, loan officers, underwriters, accountants, compliance specialists, actuaries |
| **Retail, Consumer Goods, Apparel & Food** | Major retailers, supermarket chains, food/beverage manufacturers, outdoor & apparel brands, consumer goods companies | Merchandisers, supply chain coordinators, store managers, marketing specialists, product designers |
| **Engineering, Construction & Real Estate (AEC)** | General contractors, structural/civil engineering consultancies, architecture firms, commercial real estate developers | Project managers, civil engineers, architects, estimators, site superintendents, property managers |
| **Manufacturing, Aerospace, Automotive & Defense** | Heavy manufacturing, aerospace suppliers, automotive OEMs, robotics & industrial automation, precision optics | Mechanical engineers, machinists, quality engineers, assembly technicians, plant managers |
| **Transportation, Logistics & Maritime** | Commercial airlines, freight trucking carriers, maritime shipping lines, port logistics, 3PL providers | Logistics coordinators, dispatchers, fleet operations managers, warehouse supervisors, pilots |
| **Non-Profit, Philanthropy & Global Development** | Charitable foundations, global health initiatives, humanitarian NGOs, museums, zoos, aquariums, cultural centers | Program officers, grant managers, community organizers, museum curators, fundraising directors |
| **Sports, Entertainment, Gaming & Media** | Professional sports teams, arena management, video game studios, animation/VFX houses, news publishers | Game designers, 3D animators, event coordinators, journalists, broadcast technicians, producers |
| **Enterprise Software, Cloud & Technology** | Enterprise SaaS, cybersecurity, cloud infrastructure, AI/ML platforms, IT consulting | Software engineers, product managers, DevOps/SRE, data scientists, customer success |

---

## 2. Supported ATS Platforms & Config Schemas

Every entry in `config.json` must strictly conform to [scraper/config_types.py](file:///home/brosi/job_pipeline/jobby-scraper/scraper/config_types.py). All ATS platforms are supported equally:

| Board | Required Config Key(s) | Public Endpoint Pattern | Config JSON Example |
| :--- | :--- | :--- | :--- |
| **Greenhouse** | `token` | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | `{"name": "Allen Institute", "board": "greenhouse", "token": "thealleninstitute"}` |
| **Ashby** | `slug` | `api.ashbyhq.com/posting-api/job-board/{slug}` | `{"name": "Linear", "board": "ashby", "slug": "linear"}` |
| **Lever** | `company` | `api.lever.co/v0/postings/{company}?mode=json` | `{"name": "Brooks Running", "board": "lever", "company": "brooksrunning"}` |
| **BambooHR** | `company` | `{company}.bamboohr.com/careers/list` | `{"name": "GLY Construction", "board": "bamboohr", "company": "gly"}` |
| **SmartRecruiters** | `company` | `api.smartrecruiters.com/v1/companies/{company}/postings` | `{"name": "University Health Network", "board": "smartrecruiters", "company": "universityhealthnetwork"}` |
| **Workday** | `url`, `careers_base` | `...wd<N>.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | `{"name": "Gates Foundation", "board": "workday", "url": "...", "careers_base": "..."}` |
| **Rippling** | `board_id` | `ats.rippling.com/api/v2/board/{board_id}/jobs` | `{"name": "Superhuman", "board": "rippling", "board_id": "superhuman"}` |
| **Recruitee** | `company` | `{company}.recruitee.com/api/offers` | `{"name": "Transloadit", "board": "recruitee", "company": "transloadit"}` |
| **Workable** | `company` | `apply.workable.com/api/v3/accounts/{company}/jobs` | `{"name": "Taxfix", "board": "workable", "company": "taxfix"}` |
| **Breezy** | `company` | `{company}.breezy.hr/json` | `{"name": "DuckDuckGo", "board": "breezy", "company": "duckduckgo"}` |
| **Personio** | `company` | `{company}.jobs.personio.de/xml` | `{"name": "Spryker", "board": "personio", "company": "spryker"}` |
| **Teamtailor** | `company` | `api.teamtailor.com/v1/jobs` | `{"name": "Kry", "board": "teamtailor", "company": "kry"}` |
| **Pinpoint** | `company` | `{company}.pinpointhq.com/postings.json` | `{"name": "Taxfix", "board": "pinpoint", "company": "taxfix"}` |
| **Jobvite** | `company_id` | `app.jobvite.com/CompanyJobs/Xml.aspx?c={company_id}` | `{"name": "Zillow", "board": "jobvite", "company_id": "q9x9Vfws"}` |
| **JazzHR** | `company` | `app.jazz.co/feeds/export/jobs/{company}` | `{"name": "DesignStudio", "board": "jazzhr", "company": "designstudio"}` |
| **GovernmentJobs** | `agency` | `agency.governmentjobs.com/{agency}/jobfeed.cfm` | `{"name": "City of Seattle", "board": "governmentjobs", "agency": "seattle"}` |
| **ReliefWeb** | (none) | `api.reliefweb.int/v2/jobs` | `{"name": "ReliefWeb", "board": "reliefweb"}` |
| **Oracle Cloud HCM** | `tenant`, `site_number` | `{tenant}.oraclecloud.com/hcmRestApi/.../recruitingCEJobRequisitions` | `{"name": "Enterprise Corp", "board": "oraclecloud", "tenant": "enterprise.fa.ocs", "site_number": "CX"}` |
| **SAP SuccessFactors** | `company`, `domain` | `{domain}/services/rss/job/?locale=en_US` | `{"name": "Global SAP Co", "board": "successfactors", "company": "globalsap"}` |
| **ADP Workforce Now** | `cid`, `cc_id` | `workforcenow.adp.com/mascsr/default/careercenter/public/static/v1/reqs` | `{"name": "Midland Mfg", "board": "adp", "cid": "...", "cc_id": "19000101_000001"}` |
| **Paylocity** | `guid` | `recruiting.paylocity.com/recruiting/v2/api/feed/jobs/{guid}` | `{"name": "Apex Healthcare", "board": "paylocity", "guid": "..."}` |
| **iCIMS** | `tenant`, `domain` | `{tenant}.icims.com/jobs/search?pr={page}&in_iframe=1` | `{"name": "Pacific Transit", "board": "icims", "tenant": "careers-pacifictransit"}` |
| **Jibe** | `tenant` or `url` | `{base_url}/api/jobs?page={page}&limit={limit}` | `{"name": "GitHub", "board": "jibe", "tenant": "githubinc"}` |

---


## 3. Autonomous Expansion Runbook

When researching or expanding any target region or theme:

### Step 1: Broad Cross-Field Candidate Identification
1. Review the **Industry Coverage Matrix** and build a diversified candidate employer list across healthcare, education, utilities, retail, construction, manufacturing, finance, non-profit, culture, and tech.
2. Compile candidate identifiers (corporate names, web domains, and candidate slug variations).

### Step 2: Multi-ATS Probing
Execute [scripts/discover_companies.py](file:///home/brosi/job_pipeline/jobby-scraper/scripts/discover_companies.py) to probe all supported ATS platforms concurrently:

```bash
# Probe single company across all ATS engines
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name"

# Probe candidate slugs across all ATS engines
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --company "Company Name" --slug "slug1,slug2,slug3"

# Batch probe a diversified list of companies across all fields
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --file regional_employers.txt

# Automatically append verified entries into config.json and test
PYTHONPATH=. /usr/bin/python3 scripts/discover_companies.py --file regional_employers.txt --apply --test
```

### Step 3: Web Research for Custom/Complex Endpoints
For institutions with custom domains or enterprise portals:
1. Search the web for `"[Employer Name]" ("greenhouse.io" OR "ashbyhq.com" OR "lever.co" OR "bamboohr.com" OR "smartrecruiters.com" OR "myworkdayjobs.com" OR "workable.com" OR "rippling.com")`.
2. Extract the canonical identifier or API endpoint.
3. Validate using `discover_companies.py` or by running the board's scraper class directly.

### Step 4: Verification & Live Smoke Testing
1. **Deduplication**: Verify the company or endpoint signature does not already exist in `config.json`.
2. **Live Scraper Validation**: Execute a live smoke test to confirm jobs parse cleanly:
   ```bash
   PYTHONPATH=. /usr/bin/python3 -m scraper.main --company "<Employer Name>" --limit 1 --verbose
   ```

### Step 5: Mandatory Pre-Commit & Pre-Push CI Verification
**CRITICAL**: Every agent MUST run and verify the full local CI pipeline before creating any git commit or pushing to remote. Never push without passing CI checks locally.

Execute the CI runner:
```bash
./scripts/ci.sh
```

Or execute each check individually (all must pass with exit code `0`):
1. **Test Suite**: `python -m pytest -q` (all 230+ tests must pass)
2. **Type Checking**: `python -m pyright` (strict mode, 0 errors, 0 warnings)
3. **Strict Type Audit**:
   ```bash
   if grep -rn '\bAny\b' scraper tests; then echo "Found 'Any'" && exit 1; fi
   if grep -rn 'type: ignore\|pyright: ignore' scraper tests; then echo "Found suppression comment" && exit 1; fi
   ```
4. **Code Formatting & Linting**:
   ```bash
   python -m ruff format --check .
   python -m ruff check .
   ```
   *If formatting or linting errors are found, run `python -m ruff format .` and `python -m ruff check --fix .`, re-verify with `./scripts/ci.sh`, and only then proceed.*

### Step 6: Presentation & Version Control
1. Present the discovered companies cleanly grouped by their specific **industry sector** with active job counts and ATS engine.
2. Commit and push changes only after the local CI verification has passed 100%.

