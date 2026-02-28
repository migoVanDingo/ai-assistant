# Morning Brief Collector (`briefbot`)

`briefbot` is a local ingestion + radar + retrieval pipeline.
It collects from feeds/APIs, stores all items in SQLite, clusters storylines, and exports digest views. It also supports item-level retrieval/citation/LLM summarization for OpenClaw-style workflows.

## Features

- Source ingestion: `rss`, `site`, `hn`, `arxiv`
- SQLite history + dedupe (long-lived dataset)
- Radar layer: clustering, trends, follow-up detection
- Export views: `highlights`, `balanced`, `opportunities`, `trends`, `followups`, `topics`
- Retrieval layer:
  - `find` ranked search
  - `cite` stable citation block
  - `get` article fetch/extract/cache
  - `context` LLM-ready context bundle
  - `summarize` cached LLM summaries
- Executive brief layer:
  - two-stage LLM synthesis for the daily brief (`What’s going on`, `What’s trending`)
  - excerpt + stage-1 JSON caching in SQLite
- `.env` configuration support

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Environment Variables

- `BRIEFBOT_DB_PATH` (default `data/briefbot.db`)
- `BRIEFBOT_CACHE_DIR` (default `data/article_cache`)
- `BRIEFBOT_SUMMARY_DIR` (default `data/summaries`)
- `BRIEFBOT_LLM_PROVIDER` (default `anthropic`)
- `BRIEFBOT_LLM_MODEL` (default `claude-haiku-latest`, falls back to 3.5/3 Haiku aliases)
- `BRIEFBOT_MODEL_FOR_SUMMARIES` (optional override for executive brief synthesis)
- `BRIEFBOT_ENABLE_EXEC_SUMMARY` (default `true`)
- `BRIEFBOT_MAX_CHARS_PER_ARTICLE` (default `12000`)
- `BRIEFBOT_N_TOP_LINKS_TO_SUMMARIZE` (default `10`)
- `BRIEFBOT_N_TRENDS_TO_SUMMARIZE` (default `5`)
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

## Core Commands

### Collect

```bash
python -m briefbot collect
python -m briefbot collect --refresh-discovery
```

### Cluster

```bash
python -m briefbot cluster --date today --window-days 14
```

### Export

```bash
python -m briefbot export --date today --view highlights --limit 50
python -m briefbot export --date today --view balanced --limit 50
python -m briefbot export --date today --view opportunities --limit 30
python -m briefbot export --date today --view trends --limit 30
python -m briefbot export --date today --view followups --limit 30
python -m briefbot export --date today --view topics --limit 30
```

### Run End-to-End

```bash
python -m briefbot run --limit 50
```

`run` performs collect -> cluster -> exports all configured views.

### Morning Brief

```bash
python -m briefbot morning-brief --date today
python -m briefbot morning-brief --date today --no-exec-summary
python -m briefbot morning-brief --date today --exec-summary-model claude-haiku-latest
```

`morning-brief` runs collect -> cluster -> exports -> writes a single daily markdown brief. By default it adds two executive sections at the top:

- `What’s going on`: synthesis of the top Top Links items
- `What’s trending`: synthesis of the top Trends clusters

Example section layout:

```md
# Morning Brief 2026-02-28

## What’s going on
...narrative synthesis...

## What’s trending
...narrative synthesis...

## Top Links
1. [...]

## Trends
1. [...]

## Opportunities
1. [...]

## Followups
1. [...]

## Today’s Moves
1. Read: [...]
```

## Retrieval Commands (OpenClaw-friendly)

### Find

```bash
python -m briefbot find --q "agentic eval framework" --date today --limit 20
python -m briefbot find --q "cve sandbox" --json
```

### Cite

```bash
python -m briefbot cite --item <item_id>
python -m briefbot cite --item <item_id> --format json
```

### Get (fetch + extract + cache article text)

```bash
python -m briefbot get --item rank:12 --date today
python -m briefbot get --item <item_id> --force
```

### Context (LLM-ready payload)

```bash
python -m briefbot context --item rank:12 --date today --mode summary
python -m briefbot context --item rank:12 --date today --mode full --max-chars 12000
```

### Summarize (LLM + cache)

```bash
python -m briefbot summarize --item rank:12 --date today
python -m briefbot summarize --item <item_id> --provider openai --model gpt-4o-mini
```

## OpenClaw Workflow Example

If the user asks: "summarize item 12 from today",

1. `python -m briefbot summarize --item rank:12 --date today`
2. optionally `python -m briefbot context --item rank:12 --date today --mode full`
3. paste output into chat.

## Outputs

- DB: `data/briefbot.db`
- Digest files: `data/daily_digest/YYYY-MM-DD.<view>.json|md`
- Article cache: `data/article_cache/<item_id>.txt` and `.llm.txt`
- Summaries: DB `summaries` table + `data/summaries/<item_id>.<provider>.<model>.md`
- Executive brief cache: DB `exec_summary_cache` table

## Source Config Fields

Each source supports:

- `id`, `type`, `name`, `tags`, `weight`
- `category` (`ai_research|ai_industry|devtools|mlops_infra|security|tech_news|aggregator|papers`)
- `tier` (`1..3`)
- `max_daily` (optional cap, useful for aggregators)

Type-specific:

- `rss`: `url`
- `site`: `url`
- `hn`: `mode`, `limit`, optional `keyword`
- `arxiv`: `mode`, plus `arxiv_category` or `query`
