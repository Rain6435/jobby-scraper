---
title: Parsing single links
description: Turn one job posting URL into a normalized job record, optionally saving it to the database.
---

`scraper/link_parser.py` takes the URL of a single posting and returns the same `Job` shape the board scrapers produce. It is useful for apps that let a user paste a link to a job that is not in the pool.

## Usage

```bash
# Through the main CLI
python -m scraper.main --url "<job_url>"
python -m scraper.main --url "<job_url>" --database "sqlite:///jobs.db"

# Standalone
python -m scraper.link_parser "<job_url>"
python -m scraper.link_parser --url "<job_url>" --database "sqlite:///jobs.db" --verbose
```

The job is printed to stdout as JSON (every field of the [`Job` model](/jobby-scraper/reference/job-model/)). With `--database`, it is written using a write scoped to that job's company, so only that company's rows are replaced. The exit code is `1` if parsing fails.

## How a URL is resolved

1. **Known ATS patterns.** The URL is matched against dedicated parsers, which call the board's own API for that one posting: Workday, Greenhouse, Ashby, Lever, SmartRecruiters, Rippling, BambooHR, Workable and GC Jobs (Government of Canada).
2. **Redirects.** If nothing matched, the page is fetched with redirects followed, and the final URL is tried against the same parsers. This catches vanity links and URL shorteners that land on an ATS.
3. **Generic HTML.** Otherwise the page's Schema.org `JobPosting` JSON-LD is used, falling back to OpenGraph and HTML meta tags.

Where the company can be matched to an entry in `config.json`, the canonical company name and blurb from the config are used, so the job's id lines up with jobs from regular scrapes.

## From Python

```python
from scraper.link_parser import parse_job_url, job_to_dict

job = parse_job_url("https://jobs.lever.co/acme/1234-abcd")
print(job_to_dict(job))
```

`parse_job_url` raises `ValueError` for an empty URL and `JobParseError` when a page cannot be fetched or parsed.
