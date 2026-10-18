---
title: Reliability and performance
description: Retries, concurrency, per-company timeouts, sharding and write retries.
---

A full run touches well over a thousand hosts and makes tens of thousands of requests. These are the mechanisms that keep one bad host, one big employer or one locked database from ruining the run.

## Retrying sessions

Every board builds its HTTP session with `make_session()` in [`scraper/boards/base.py`](https://github.com/Rain6435/jobby-scraper/blob/main/scraper/boards/base.py). It mounts a `urllib3.Retry` that:

- retries up to 4 times on `429`, `500`, `502`, `503` and `504`, for both `GET` and `POST`;
- backs off exponentially (1.5 s, 3 s, 6 s, 12 s);
- honors a `Retry-After` header;
- keeps a connection pool of 16, matching the detail-fetch thread pool, so connections are reused.

This is why a Workday tenant returning 429 under load no longer drops that company for the whole run.

## Failure isolation

Each company's scrape runs inside a broad `try/except` once retries are exhausted. An exception is logged with its traceback, the company is counted as failed, and its previous jobs are kept. Only when **every** company in a batch fails does the batch exit with code 1 without writing, leaving the previous snapshot untouched.

## Concurrency

`--concurrency` (default 16) companies are scraped at once in a `ThreadPoolExecutor`. Because most companies sit on different hosts, raising it mostly increases cross-host throughput rather than the request rate against one server.

Inside a company, boards that need a detail request per posting run those requests in their own pool of 16 threads (`DETAIL_FETCH_WORKERS`). Only cache misses hit the network.

## Per-company timeout

A company still running after `--per-company-timeout` seconds (default 120) is treated as a straggler:

1. A fresh attempt for that company is queued, and the rest of the batch keeps moving.
2. The original attempt is not killed (Python cannot safely interrupt a thread blocked in a network call). Its result, whenever it arrives, is discarded.
3. A company that stalls on 2 consecutive attempts is counted as failed for the run and its previous jobs are carried forward.

Pass `--per-company-timeout 0` to wait on every company indefinitely.

When the CLI finishes, it exits with `os._exit()` rather than a normal interpreter shutdown, so an abandoned thread still waiting on a dead connection cannot delay the process exit.

## Sharding

By default a full run is one batch: the entire previous pool and the entire current pool live in memory together, and everything is written at the end.

`--shard-size N` splits the run into batches that are each loaded, scraped, diffed and written independently:

- **Memory** is bounded by one shard's jobs instead of the whole pool's.
- **Failures** are contained: a shard that fails does not lose the shards that succeeded.
- **Writes** are scoped. A sharded write deletes and reinserts only that shard's companies' jobs. Shared lookup tables (companies, sources, locations) are never wiped by a scoped write, because other shards' rows still reference them.

Shards are filled greedily in `config.json` order up to `--shard-job-target` jobs (default 20,000), using each company's job count from the previous run, and never exceed `N` companies. A single company bigger than the target gets a shard of its own. Without previous counts (the first run), shards are simply N companies each.

## Database writes

`write_jobs()` does not hold one giant transaction. It deletes, then inserts lookup rows, then inserts jobs and job locations in chunks of 750 rows, each in its own short transaction. On SQLite that keeps the writer lock short enough that other processes reading the same file are not starved. The cost is that a concurrent reader can see a partially written pool for a moment.

Other safeguards:

- SQLite connections use a 60 second busy timeout and WAL journaling.
- A failed write is retried up to 5 times, with backoff of 5, 10, 20 and 30 seconds. If all attempts fail the run exits with code 1; a write failure is never silently reported as success.
- After writing, SQLite's WAL is checkpointed with `TRUNCATE` so the `-wal` file does not grow without bound.
- On failure, the log says which stage (`delete`, `lookups`, `jobs` and so on) the write reached, so a partial write can be told apart from no write.

## Interrupts

Ctrl-C during scraping saves the companies that finished, carries every unfinished company forward from the previous snapshot, and exits with code 130. With several shards, the remaining shards still run.
