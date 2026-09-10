# Shopify Careers Platform Documentation

## Overview
Shopify hosts its primary in-house careers platform at:
`https://www.shopify.com/careers`

While Shopify previously utilized SmartRecruiters (and uses Ashby as an internal backend), its public-facing portal is built on React Router / Remix with server-rendered listing HTML and `.data` JSON endpoints for individual postings:
`https://www.shopify.com/careers/{slug}_{uuid}.data`

## Endpoints
1. **List Page**:
   - `GET https://www.shopify.com/careers`
   - Returns SSR HTML with all active job postings embedded inside anchor cards:
     `<a href="/careers/{slug}_{uuid}"> ... <h4>{title}</h4> ... <span class="... uppercase ...">{location}</span></a>`
2. **Posting Detail**:
   - `GET https://www.shopify.com/careers/{slug}_{uuid}.data`
   - Returns React Router serialized stream containing `publishedDate` (ISO `YYYY-MM-DD`), full plain-text/HTML job descriptions, team names, and employment types.

## Pipeline Mapping
- **`Job.id`**: `f"shopify:{uuid}"`
- **`Job.title`**: Extracted from `<h4>` title element
- **`Job.location`**: Cleaned location string (e.g. `'Remote - Canada'` -> `'Remote, Canada'`)
- **`Job.locations`**: List of cleaned location strings
- **`Job.url`**: `https://www.shopify.com/careers/{slug}_{uuid}`
- **`Job.posted_date`**: `publishedDate` extracted from detail `.data`
- **`Job.posted_days`**: Calculated days since `publishedDate`
- **`Job.description`**: Full text extracted from `descriptionPlain` / `descriptionHtml`
- **`Job.source`**: `"shopify"`
