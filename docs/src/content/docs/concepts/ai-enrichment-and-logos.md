---
title: AI enrichment and logos
description: Company blurbs, role summaries, LLM provider selection, Ollama key rotation and company logos.
---

Everything on this page is optional. With no API keys configured, the pipeline runs normally and the AI fields stay empty strings.

## Company blurbs

A blurb is one or two sentences about what a company does. It is generated **once per company**, stored in that company's `config.json` entry as `"blurb"`, and copied onto the `companies.blurb` column on every write.

```bash
python -m scraper.backfill_blurbs            # only companies missing a blurb
python -m scraper.backfill_blurbs --dry-run
python -m scraper.backfill_blurbs --force    # regenerate every blurb
```

The scrape itself never calls the AI for blurbs. Hand-written blurbs are fine too.

## Role summaries

`jobs.role_summary` is meant to hold a short summary of what one posting involves day to day. **The scraper no longer generates it.** Generating it during the scrape made AI cost scale with the number of new jobs and slowed runs badly whenever a provider was degraded. New jobs are written with an empty summary, and the consumer project fills it in later with its own model, writing directly to the database.

Once a summary exists, the scraper preserves it: known jobs carry their `role_summary` forward on every run. `summarize_role()` in `scraper/summarize.py` still exists if you want to call it yourself.

## Providers

`scraper/summarize.py` tries providers in order and never raises:

1. **Anthropic** (`claude-haiku-4-5`), using `ANTHROPIC_API_KEY`, or `ANTHROPIC_AUTH_TOKEN` such as a Claude Code OAuth token. The API key wins if both are set.
2. **Ollama Cloud** (`gemma4:31b`), using `OLLAMA_API_KEY`. Used when Anthropic is not configured or its call fails. `gemma4:31b` is a non-reasoning model available on the free tier.

Any failure logs a warning and moves on to the next provider, or returns `""` when none is left.

To pin to one provider, set `LLM_PROVIDER=anthropic` or `LLM_PROVIDER=ollama`. The other provider is then never tried, so a failure returns `""` instead of silently falling back. `auto` or unset keeps the fallback. An unrecognized value is ignored with a warning.

## Ollama key rotation

Ollama Cloud's free tier has a usage limit per key (reported as an "hourly" or "session" usage limit, on roughly a five-hour clock). `OLLAMA_API_KEY` may therefore hold several comma-separated keys:

```bash
OLLAMA_API_KEY=key1,key2,key3,key4
```

When a key hits its usage limit, it is marked exhausted for 5 hours and the next key is used immediately. A transient "too many concurrent requests" 429 is different: it is retried once on the same key. If every key is exhausted, the call returns `""`.

Exhaustion state is persisted to a JSON file so it survives across processes:

- `../data/ollama_key_rotation.json` when the repo is checked out inside the parent pipeline, which shares the same file and keys;
- otherwise `.ollama_key_rotation.json` in the repo root;
- or wherever `OLLAMA_KEY_ROTATION_STATE_FILE` points.

Only a short hash of each key is written to that file, never the key itself.

## Logos

Every company carries an SVG logo at `data/logos/<slug>.svg`, referenced from `config.json` as `"logo"` and copied to `companies.logo`. Logos are resolved by `scraper/logos.py` through five tiers, stopping at the first hit:

1. Curated vector libraries (Simple Icons, SVGL, VectorLogoZone).
2. The official logo from Wikidata and Wikimedia Commons.
3. An SVG logo or favicon scraped from the company's own website or careers page.
4. A high-resolution raster favicon, embedded in a 128 by 128 SVG.
5. A generated geometric monogram with a color derived from the company name.

Every result is normalized into the same 128 by 128 SVG canvas, and the last tier always succeeds, so every company has a logo.

```bash
python -m scraper.backfill_logos                      # companies without a logo file
python -m scraper.backfill_logos --company "Acme"
python -m scraper.backfill_logos --force --workers 32
python -m scraper.backfill_logos --dry-run
```

`scripts/discover_companies.py --apply` resolves logos for the companies it adds. `scripts/backfill_companies_logo_column.py` copies logo paths into an existing database's `companies.logo` column.
