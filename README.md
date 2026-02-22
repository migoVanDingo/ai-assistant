# Morning Brief Collector (`briefbot`)

`briefbot` is a Python ingestion pipeline for collecting daily links from RSS/Atom feeds, Hacker News, and arXiv.
It does ingestion + normalization + scoring + export only (no LLM usage).

## Features

- Config-driven sources from a single `sources.yaml` (supports large lists)
- Source types:
  - `rss`: explicit feed URL
  - `site`: homepage with auto-discovered RSS/Atom links
  - `hn`: Hacker News (`top`, `new`, `best`) with optional keyword filtering
  - `arxiv`: category RSS or query via arXiv API fallback
- SQLite storage for history + dedupe + feed cache
- URL canonicalization and dedupe across runs
- ETag / Last-Modified caching for feeds
- Scoring based on recency, source weight, keywords, and HN metrics
- Daily exports to JSON + Markdown

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## CLI Usage

### Collect

```bash
python -m briefbot collect
```

Optional flags:

```bash
python -m briefbot collect --config sources.yaml --db data/briefbot.db --dry-run
```

### Export

```bash
python -m briefbot export --date today --limit 50
```

Optional tag filters:

```bash
python -m briefbot export --date 2026-02-22 --include-tags ai,security --exclude-tags startups
```

### Run (collect + export)

```bash
python -m briefbot run --limit 50
```

## Output

- Database: `data/briefbot.db`
- Daily exports:
  - `data/daily_digest/YYYY-MM-DD.json`
  - `data/daily_digest/YYYY-MM-DD.md`

JSON output contains:

- `date`
- `count`
- `items[]` with normalized schema fields (`item_id`, `source_id`, `title`, `url`, `published_at`, `tags`, `metrics`, `score`, etc.)

## Source Config (`sources.yaml`)

Each source has:

- `id` (unique)
- `type` (`rss` | `site` | `hn` | `arxiv`)
- `name`
- `tags` (list)
- `weight` (float)

Type-specific fields:

- `rss`: `url`
- `site`: `url`
- `hn`: `mode` (`top|new|best`), `limit`, optional `keyword`
- `arxiv`: `mode` (`category|query`), and `category` or `query`, plus `limit`

## Dedupe Rules

- Canonical URL normalization removes common tracking params and fragments.
- Primary dedupe key: canonical URL.
- Fallback dedupe key when URL is unavailable: hash of title + source + published time.
- Duplicates are not reinserted; `last_seen_at` is updated.

## Notes

- Errors are isolated per source; one bad source does not fail whole collection.
- `site` feed discovery is cached for 7 days in SQLite.
- `rss` sources that return `404/410` automatically try homepage feed discovery as a fallback.
- Optional per-source `verify_ssl: false` can be used for feeds with broken certificates.
- Works on Linux and other Unix-like systems with Python 3.11+.
