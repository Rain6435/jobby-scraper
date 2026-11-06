---
title: Environment variables
description: Every environment variable the scraper reads.
---

All are optional. They can be exported or put in a `.env` file at the repo root (copy [`.env.example`](https://github.com/Rain6435/jobby-scraper/blob/main/.env.example)).

| Variable | Used by | Description |
| -------- | ------- | ----------- |
| `ANTHROPIC_API_KEY` | AI helpers | Anthropic API key. Tried first for company blurbs. |
| `ANTHROPIC_AUTH_TOKEN` | AI helpers | Alternative to the API key, e.g. a Claude Code OAuth token. The API key wins if both are set. |
| `OLLAMA_API_KEY` | AI helpers | One or more comma-separated Ollama Cloud keys. Fallback provider, with automatic rotation when a key hits its usage limit. |
| `OLLAMA_API_ENDPOINT` | AI helpers | Ollama base URL. Default `https://ollama.com`; override for a self-hosted Ollama. |
| `OLLAMA_KEY_ROTATION_STATE_FILE` | AI helpers | Where key-exhaustion state is stored. Default `../data/ollama_key_rotation.json` when nested in the parent pipeline, else `.ollama_key_rotation.json`. |
| `LLM_PROVIDER` | AI helpers | `anthropic` or `ollama` to use only that provider; `auto` or unset for the fallback order. |
| `USAJOBS_API_KEY` | `usajobs` board | Free key from [developer.usajobs.gov](https://developer.usajobs.gov/). Without it the board contributes no jobs. |
| `USAJOBS_USER_AGENT` | `usajobs` board | The email address registered with that key. |
| `LOG_LEVEL` | `scraper.main` | `DEBUG`, `INFO` (default), `WARNING` or `ERROR`. `--verbose` overrides it with `DEBUG`. |
| `SCRAPER_SQLITE_CACHE_KIB` | `scraper.db` | SQLite page cache per connection, in KiB. Default `64000`. Lower it on small instances; see [Reliability and performance](/jobby-scraper/concepts/reliability-and-performance/#running-on-a-small-instance). |

The scrape itself makes no AI calls, so only `USAJOBS_*`, `LOG_LEVEL` and `SCRAPER_SQLITE_CACHE_KIB` affect a normal run.
