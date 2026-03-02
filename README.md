# Morning Brief Collector (`briefbot`)

`briefbot` is a local ingestion + radar + retrieval pipeline.
It collects from feeds/APIs, stores all items in SQLite, clusters storylines, exports digest views, writes a daily markdown brief, and serves a dashboard for browsing/querying the archive.

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
- Nightly automation:
  - `briefbot/nightly_briefbot.sh` runs collect/cluster/topics/exports/brief composition
  - optional Telegram notification when a target is configured
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
- `BRIEFBOT_BRIEF_DIR` (default `data/briefs`)
- `BRIEFBOT_CACHE_DIR` (default `data/article_cache`)
- `BRIEFBOT_SUMMARY_DIR` (default `data/summaries`)
- `BRIEFBOT_LLM_PROVIDER` (default `anthropic`)
- `BRIEFBOT_LLM_MODEL` (default `claude-haiku-latest`, falls back to 3.5/3 Haiku aliases)
- `BRIEFBOT_MODEL_FOR_SUMMARIES` (optional override for executive brief synthesis)
- `BRIEFBOT_ENABLE_EXEC_SUMMARY` (default `true`)
- `BRIEFBOT_MAX_CHARS_PER_ARTICLE` (default `12000`)
- `BRIEFBOT_N_TOP_LINKS_TO_SUMMARIZE` (default `10`)
- `BRIEFBOT_N_TRENDS_TO_SUMMARIZE` (default `5`)
- `BRIEFBOT_DIGEST_DIR` (optional override for digest output in the nightly script)
- `BRIEFBOT_LOG_DIR` (optional override for nightly logs)
- `BRIEFBOT_ENV_FILE` (optional `.env` path)
- `BRIEFBOT_TELEGRAM_TARGET` (optional Telegram target for nightly notifications)
- `BRIEFBOT_GREETING_NAME` (optional greeting name in the nightly Telegram message; default `there`)
- `OPENCLAW_BIN` (optional override for the OpenClaw CLI used by the nightly script)
- `DASHBOARD_BRIEFS_URL` (optional URL included in the nightly Telegram message)
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

### Nightly Automation

Run the full nightly shell workflow directly:

```bash
./briefbot/nightly_briefbot.sh
```

Or via `make`:

```bash
make nightly-briefbot
```

What the nightly script does:

- loads `.env` if present
- runs `collect`, `cluster`, `topics`
- exports `balanced`, `trends`, `opportunities`, `followups`, `topics`
- composes `data/briefs/YYYY-MM-DD.daily.md`
- optionally sends a Telegram message with the dashboard URL

Telegram behavior:

- if `BRIEFBOT_TELEGRAM_TARGET` is unset, Telegram is skipped without failing the run
- if `openclaw` is unavailable, Telegram is skipped without failing the run
- the greeting text uses `BRIEFBOT_GREETING_NAME`, so different users can customize it

### Topics

```bash
python -m briefbot topics --date today --window-days 30 --limit 50
```

`topics` recomputes topic profiles and exports the `topics` view. Topic computation remains available for exports and background jobs even though the daily brief itself omits the Topics section.

### Morning Brief

```bash
python -m briefbot morning-brief --date today
python -m briefbot morning-brief --date today --no-exec-summary
python -m briefbot morning-brief --date today --exec-summary-model claude-haiku-latest
```

`morning-brief` runs collect -> cluster -> exports -> writes a single daily markdown brief. By default it adds two executive sections at the top:

- `What’s going on`: synthesis of the top Top Links items
- `What’s trending`: synthesis of the top Trends clusters

Current daily brief layout:

- `What’s going on`
- `What’s trending`
- `Top Links` (top 10)
- `Trends` (top 5)
- `Opportunities` (top 5)
- `Followups` (top 5)
- `Today’s Moves`

The daily brief is written to:

- `data/briefs/YYYY-MM-DD.daily.md`

or `BRIEFBOT_BRIEF_DIR` if overridden.

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
python -m briefbot get --item rank:opportunities:3 --date today
python -m briefbot get --item <item_id> --force
```

### Context (LLM-ready payload)

```bash
python -m briefbot context --item rank:12 --date today --mode summary
python -m briefbot context --item rank:balanced:12 --date today --mode summary
python -m briefbot context --item rank:12 --date today --mode full --max-chars 12000
```

### Summarize (LLM + cache)

```bash
python -m briefbot summarize --item rank:12 --date today
python -m briefbot summarize --item rank:opportunities:3 --date today
python -m briefbot summarize --item <item_id> --provider openai --model gpt-4o-mini
```

Rank references supported by retrieval commands:

- `rank:N`
- `rank:<view>:N`

Examples:

- `rank:balanced:12`
- `rank:opportunities:3`
- `rank:trends:1`
- `rank:followups:2`

## OpenClaw Workflow Example

If the user asks: "summarize item 12 from today",

1. `python -m briefbot summarize --item rank:12 --date today`
2. optionally `python -m briefbot context --item rank:12 --date today --mode full`
3. paste output into chat.

## Outputs

- DB: `data/briefbot.db`
- Digest files: `data/daily_digest/YYYY-MM-DD.<view>.json|md`
- Daily briefs: `data/briefs/YYYY-MM-DD.daily.md`
- Nightly logs: `data/logs/nightly.YYYY-MM-DD.log`
- Article cache: `data/article_cache/<item_id>.txt` and `.llm.txt`
- Summaries: DB `summaries` table + `data/summaries/<item_id>.<provider>.<model>.md`
- Executive brief cache: DB `exec_summary_cache` table

## Dashboard

A React + MUI dashboard lives under `dashboard/`. It provides:

- a morning brief reader with a left-hand brief archive
- theme toggle (light/dark)
- top-level metrics cards
- an `Ask Briefbot` route backed by a DAO + LLM adapter over the SQLite DB
- recent query history persisted in SQLite and replayable without another LLM call
- a deterministic `Stories` browser with source/cluster/tag/watch-hit/date filters

Backend:

```bash
uvicorn dashboard.backend.api:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd dashboard
npm install
npm run dev
```

The frontend proxies `/api` to `http://localhost:8000` by default.

The dashboard frontend uses absolute `/api/*` requests. `VITE_API_BASE_URL` should only be set to a full `http(s)` origin. Do not set it to `/briefs` or any other path-only value.

For Tailscale Serve under `/briefs`, use:

- `/briefs` -> frontend
- `/api` -> backend

The supported production shape is a built frontend served by the included static server, not Vite dev. Tailscale Serve may forward the mounted path with the prefix removed, so the backend also accepts both `/api/*` and stripped aliases like `/metrics` and `/query` for compatibility and logging visibility.

Example runtime split:

```bash
uvicorn dashboard.backend.api:app --reload --host 127.0.0.1 --port 8000
cd dashboard
VITE_APP_BASE=/briefs/ npm run dev -- --host 127.0.0.1 --port 5173
```

Verify backend health:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/queries
curl http://127.0.0.1:8000/api/stories/sources
curl http://127.0.0.1:8000/api/stories
```

### Ask Briefbot

The Ask route uses a bounded tool router over the local SQLite archive.

- recent queries are stored in the `dashboard_queries` table
- the desktop layout shows recent queries in a left sidebar
- mobile shows recent queries in the drawer when you are on `/ask`
- selecting a past query reopens the exact stored markdown response
- item-heavy results are rendered as deterministic markdown lists with clickable links

### Stories Browser

The Stories route is deterministic and does not call an LLM.

Available filters:

- source buttons
- date from / date to
- limit selector
- cluster dropdown
- tags multiselect
- watch hits multiselect
- published-date sort order

Useful endpoints:

```bash
curl http://127.0.0.1:8000/api/stories/sources
curl http://127.0.0.1:8000/api/stories/clusters
curl http://127.0.0.1:8000/api/stories/tags
curl http://127.0.0.1:8000/api/stories/watch-hits
curl -X POST http://127.0.0.1:8000/api/stories \
  -H 'Content-Type: application/json' \
  -d '{"source_name":"arXiv","limit":10,"order":"desc"}'
```

Single-command deploy:

```bash
make deploy-dashboard
```

This deploys the current local checkout and does not pull from Git by default.

To pull first, use:

```bash
make deploy-dashboard-pull
```

This script will:

- optionally run `git pull --ff-only` when using `make deploy-dashboard-pull`
- install Python and frontend dependencies
- build the dashboard with an embedded build SHA/timestamp
- restart the FastAPI backend and static frontend server
- verify local `/api/health` and `/api/metrics`
- verify the built bundle still contains `/api/metrics`, `/api/briefs`, and `/api/query`
- verify the public Tailscale `/api/metrics` and `/briefs` endpoints when a tailnet URL is discoverable

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
