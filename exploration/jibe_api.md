# Jibe Enterprise Career Platform API

**Status: IMPLEMENTED.** Ships in `scraper/boards/jibe.py`.

Jibe (an enterprise career site platform by iCIMS) powers career portals for leading tech firms and Fortune 500 enterprises, including **GitHub**, **PepsiCo**, **FedEx**, **Costco**, **Alaska Airlines**, and **General Mills**.

Portals are either hosted on subdomains of `jibeapply.com` (e.g. `https://githubinc.jibeapply.com` or `https://pepsico.jibeapply.com`) or custom domains (e.g. `https://www.github.careers`).

## Endpoints

- **Job search / listings:**
  `GET {base_url}/api/jobs?page={page}&limit={limit}`
  - `page`: 1-indexed integer (1, 2, 3...)
  - `limit`: number of results per page (supports up to 100)
  - Default `limit` if omitted is 10.

- **Authentication:** None required. Public candidate-facing JSON endpoint.

## Response Structure

```json
{
  "totalCount": 81,
  "jobs": [
    {
      "data": {
        "slug": "5677",
        "req_id": "5677",
        "title": "Staff Software Engineer, Elasticsearch",
        "description": "<strong>About GitHub</strong><br>...",
        "create_date": "2026-09-10T09:53:10+0000",
        "posted_date": "2026-09-10T09:52:00+0000",
        "location_name": "Canada Remote",
        "full_location": "Canada",
        "city": null,
        "state": null,
        "country": "Canada",
        "country_code": "CA",
        "multipleLocations": true,
        "additional_locations": [
          {
            "location_name": "US Remote",
            "country": "United States",
            "country_code": "US"
          }
        ],
        "canonical_url": "https://githubinc.jibeapply.com/jobs/5677?lang=en-us"
      }
    }
  ]
}
```

## Mapping to `Job` Model

- `id`: `{slug}:{req_id or slug}`
- `title`: `data.title`
- `location`: `data.location_name` or `data.full_location` or joined `[city, state, country]`
- `locations`: primary location plus any entries from `data.additional_locations`
- `url`: `data.canonical_url` or `data.meta_data.canonical_url` or fallback `{base_url}/jobs/{req_id}`
- `description`: `data.description` parsed through `html_to_text()`
- `posted_date` / `posted_days`: from `data.create_date` or `data.posted_date`
- `source`: `"jibe"`

## Config Options

```json
{ "name": "GitHub", "board": "jibe", "tenant": "githubinc" }
{ "name": "GitHub", "board": "jibe", "url": "https://www.github.careers" }
{ "name": "PepsiCo", "board": "jibe", "tenant": "pepsico" }
{ "name": "Costco", "board": "jibe", "tenant": "costco" }
{ "name": "Alaska Airlines", "board": "jibe", "tenant": "alaskaair" }
```
