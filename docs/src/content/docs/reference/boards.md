---
title: Supported boards
description: Every board value accepted in config.json, the fields it needs, and what it provides.
---

The `board` field of a company entry selects its scraper from the `SCRAPERS` registry in [`scraper/boards/__init__.py`](https://github.com/Rain6435/jobby-scraper/blob/main/scraper/boards/__init__.py). Every entry also needs `name`; see [Configuration](/jobby-scraper/reference/configuration/) for the fields shared by all boards.

**Date** shows where `posted_days` comes from. Boards marked **none** leave it empty, so `posted_date` is `NULL` and consumers should use `first_seen`.

**Detail** shows whether the board makes one extra request per posting. Those requests are cached between runs (see [the detail cache](/jobby-scraper/concepts/job-identity-and-diffing/#the-detail-cache)). "Optional" means it is controlled by a `fetch_details` config flag, with the default shown.

**Count** is the number of entries in `config.json` at the time of writing.

## Applicant tracking systems

These are hosted ATSes used by many employers. One entry per company.

| `board` | Platform | Required fields | Optional fields | Date | Detail | Count |
| ------- | -------- | --------------- | --------------- | ---- | ------ | ----: |
| `greenhouse` | Greenhouse | `token` | | `first_published` | no | 309 |
| `workday` | Workday | `url` (the `/wday/cxs/.../jobs` API URL) | `careers_base` | `postedOn` | yes | 299 |
| `ashby` | Ashby | `slug` | | `publishedAt` | no | 148 |
| `successfactors` | SAP SuccessFactors (Career Site Builder RSS) | `company` | `domain` (default `jobs.<company>.com`), `rows` (default 2000) | `pubDate` | no | 122 |
| `bamboohr` | BambooHR | `company` (subdomain) | | none | yes | 93 |
| `smartrecruiters` | SmartRecruiters | `company` (identifier) | | `releasedDate` | yes | 78 |
| `lever` | Lever | `company` (slug) | | `createdAt` | no | 51 |
| `oraclecloud` | Oracle Cloud HCM Candidate Experience | `tenant` (subdomain or host) | `site_number` (default `CX`) | `PostedDate` | no | 37 |
| `phenom` | Phenom People | `url` (portal search base, e.g. `https://careers.opentext.com/us/en`) | `location`, `category`, `keyword`, `max_pages`, `fetch_details` | `postedDate` | optional, off | 24 |
| `governmentjobs` | GovernmentJobs (NEOGOV) RSS | `agency` | | `pubDate` | no | 20 |
| `rippling` | Rippling | `board_id` | | none | yes | 19 |
| `teamtailor` | Teamtailor | `company` (subdomain) | | `date_published` | no | 10 |
| `pinpoint` | Pinpoint | `company` (subdomain) | | `created_at` | no | 10 |
| `jibe` | Jibe (iCIMS enterprise search) | `tenant` or `url` | `max_pages` | `create_date` | no | 9 |
| `breezy` | Breezy HR | `company` (subdomain) | | `published_date` | no | 8 |
| `workable` | Workable | `company` (account slug) | | `published_on` | no | 8 |
| `recruitee` | Recruitee | `company` (subdomain) | | `published_at` | no | 8 |
| `jazzhr` | JazzHR XML feed | `company` (subdomain) | | none | no | 7 |
| `personio` | Personio XML feed | `company` (subdomain) | | `createdAt` | no | 4 |
| `icims` | iCIMS candidate portal | `tenant` | `domain` | `Posted Date` | no | 4 |
| `bloomberg` (alias `avature`) | Avature portals (Bloomberg and others) | | `url`, `query`, `location`, `max_pages` | none | no | 3 |
| `jobvite` | Jobvite XML feed | `company_id` (companyEId) | | `date` | no | 2 |
| `adp` | ADP Workforce Now | `cid` | `cc_id` (default `19000101_000001`) | `postDate` | no | 0 |
| `paylocity` | Paylocity Job Feed V2 | `guid` | | `postedDate` | no | 0 |

## Single-employer portals

Custom careers sites for one employer each. One entry covers the whole company.

| `board` | Site | Optional fields | Date | Detail | Count |
| ------- | ---- | --------------- | ---- | ------ | ----: |
| `amazon` | amazon.jobs | `category`, `country`, `business_category`, `max_pages` | yes | no | 1 |
| `apple` | jobs.apple.com | `search`, `location`, `team`, `max_pages` | yes | no | 1 |
| `google` | Google Careers | `query`, `location`, `company_name`, `max_pages` | yes | no | 2 |
| `microsoft` | Microsoft Careers | `query`, `location`, `max_pages`, `fetch_details` | yes | optional, on | 1 |
| `meta` | metacareers.com | `query` | none | no | 1 |
| `netflix` | Netflix (Eightfold) | `query`, `location`, `max_pages`, `fetch_details` | yes | optional, on | 1 |
| `atlassian` | Atlassian Careers | `category`, `location`, `keyword` | `updatedDate` | no | 1 |
| `shopify` | shopify.com/careers | `location`, `keyword`, `fetch_details` | from detail | optional, on | 1 |
| `ibm` | IBM Careers | | none | no | 1 |
| `ea` | jobs.ea.com | `search`, `max_pages`, `fetch_details` | none | optional, off | 1 |
| `tiktok` | lifeattiktok.com | `keyword`, `max_pages` | none | no | 1 |
| `valve` | valvesoftware.com/jobs | `fetch_details` | none | optional, on | 1 |
| `janestreet` | janestreet.com | `location` | none | no | 1 |

## Aggregators and public-sector boards

One entry covers a whole board with many employers. `Job.company` is set per posting from the board's own organization field.

| `board` | Source | Config | Date | Detail | Count |
| ------- | ------ | ------ | ---- | ------ | ----: |
| `usajobs` | USAJobs search API (US federal) | needs `USAJOBS_API_KEY` and `USAJOBS_USER_AGENT` env vars | yes | no | 1 |
| `gc_jobs` (alias `gcjobs`) | GC Jobs, Government of Canada | `title`, `department`, `location`, `language`, `max_pages`, `fetch_details`, `resolve_transitions` | none | optional, off | 1 |
| `quebec_emploi` (alias `emploi_quebec`) | Québec emploi | `title`, `query`, `location`, `region`, `regions`, `language`, `max_pages`, `fetch_details` | none | optional, off | 1 |
| `reliefweb` | ReliefWeb API (UN and humanitarian NGOs) | | `date.created` | no | 0 |
| `climatebase` | Climatebase | `keywords` | yes | no | 1 |
| `cma_heritage` | Canadian Museums Association, Jobs in Heritage | | none | no | 1 |
| `cip_planning` | Canadian Institute of Planners job board | | yes | no | 1 |
| `idc_career_centre` | Interior Designers of Canada career centre | | yes | no | 1 |

`gc_jobs` sets each posting's `company` to the hiring department and its `company_group` (stored as `companies.group_name`) to the config entry's name, so consumers can group the departments together.

## Notes

- **Search options are not filters for the pool.** Some custom portals accept `query`, `keyword`, `location` or `category` to narrow what they fetch. None of the current `config.json` entries use them; the pool is meant to hold every listing.
- **Workday** pagination is capped at 500 jobs per company. The detail request also expands multi-location postings ("12 Locations") into their real location list.
- **SmartRecruiters** needs the detail request for the posting URL as well as the description.
- **Personio** feeds carry no job URL; it is built as `https://<company>.jobs.personio.de/job/<id>`.
- Board research notes for the custom portals live in [`exploration/`](https://github.com/Rain6435/jobby-scraper/tree/main/exploration).
