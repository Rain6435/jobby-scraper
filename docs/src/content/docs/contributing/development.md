---
title: Development
description: Tests, type checking, linting and working on the docs site.
---

## Quality gates

CI ([`.github/workflows/ci.yml`](https://github.com/Rain6435/jobby-scraper/blob/main/.github/workflows/ci.yml)) runs on every push to `main` and every pull request, on Python 3.12:

| Job | What it checks |
| --- | -------------- |
| `test` | `python -m pytest -q` |
| `typecheck` | `pyright` in strict mode, plus a grep that fails on any `Any` or any `type: ignore` / `pyright: ignore` comment in `scraper/` or `tests/` |
| `lint` | `ruff format --check .` and `ruff check .` (rules `E`, `F`, `I`, `UP`; 100-character lines) |

Run the same gates locally:

```bash
bash scripts/ci.sh
```

The script picks up `.venv` if present, and uses `pytest -n auto` when `pytest-xdist` is installed.

### Strict typing

There is no `Any` anywhere in `scraper/` or `tests/`, and no suppression comments. Describe JSON responses with `TypedDict` and narrow with `cast()` where a library returns an untyped value. Fix the type rather than silencing the checker.

## Tests

```bash
python -m pytest                        # everything
python -m pytest tests/test_workday.py  # one file
python -m pytest -n auto                # in parallel
```

Board tests mock HTTP with [`responses`](https://github.com/getsentry/responses) and fixtures in `tests/fixtures/`; no test touches the network. Pipeline tests inject fakes through `RunDeps` in `scraper/main.py` instead of monkeypatching module globals.

When you add a board, add `tests/test_<board>.py` covering the mapping from the API response to `Job` fields, including the id format and any date parsing.

## Project notes

[`CLAUDE.md`](https://github.com/Rain6435/jobby-scraper/blob/main/CLAUDE.md) at the repo root is the detailed design log: why each mechanism exists and which production incidents shaped it. Read it before changing the pipeline, the database layer or the detail cache.

## Working on these docs

The site is an [Astro Starlight](https://starlight.astro.build/) project in `docs/`.

```bash
cd docs
npm install
npm run dev      # http://localhost:4321/jobby-scraper/
npm run build    # static site in docs/dist/
```

Pages are Markdown or MDX files in `docs/src/content/docs/`. The sidebar is defined in `docs/astro.config.mjs`. Internal links include the `/jobby-scraper/` base path because the site is served from GitHub Pages at `https://rain6435.github.io/jobby-scraper/`.

The [Docs workflow](https://github.com/Rain6435/jobby-scraper/blob/main/.github/workflows/docs.yml) builds the site on pull requests that touch `docs/`, and deploys it to GitHub Pages on pushes to `main`.
