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
  - configurable notification backend: `mailgun` (default, no OpenClaw required) or `openclaw` (Telegram)
- macOS launchd services for persistent dashboard and nightly scheduling
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
- `BRIEFBOT_NOTIFICATION_BACKEND` (default `mailgun`; set to `openclaw` or `none`)
- `MAILGUN_SENDING_API_KEY` (Mailgun sending key; required when using `mailgun` backend)
- `MAILGUN_DOMAIN` (Mailgun domain; required when using `mailgun` backend)
- `MAILGUN_API_BASE` (optional; override to `https://api.eu.mailgun.net/v3` for EU accounts)
- `BRIEFBOT_EMAIL_TO` (recipient address for nightly email)
- `BRIEFBOT_EMAIL_FROM` (sender address for nightly email)
- `BRIEFBOT_TELEGRAM_TARGET` (Telegram target; only used when `BRIEFBOT_NOTIFICATION_BACKEND=openclaw`)
- `BRIEFBOT_GREETING_NAME` (greeting name in the nightly notification; default `there`)
- `OPENCLAW_BIN` (optional override for the OpenClaw CLI; only used when `BRIEFBOT_NOTIFICATION_BACKEND=openclaw`)
- `DASHBOARD_BRIEFS_URL` (URL included in the nightly notification; set to your Tailscale URL)
- `PROJECT_DIR` (optional override for the nightly script project root)
- `BRIEFBOT_DATA_DIR` (optional override for the nightly script data root)
- `VITE_APP_BASE` (optional dashboard frontend base path)
- `VITE_API_BASE_URL` (optional full-origin dashboard API base URL)
- `VITE_ALLOWED_HOSTS` (optional comma-separated Vite dev-server allowed hosts)
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
- activates `.venv` if present
- runs `collect`, `cluster`, `topics`
- exports `balanced`, `trends`, `opportunities`, `followups`, `topics`
- composes `data/briefs/YYYY-MM-DD.daily.md`
- sends a notification with the dashboard URL (channel depends on `BRIEFBOT_NOTIFICATION_BACKEND`)

Notification behavior:

- controlled by `BRIEFBOT_NOTIFICATION_BACKEND` (default: `mailgun`)
- notifications are skipped gracefully (never fail the run) if credentials are missing
- `BRIEFBOT_GREETING_NAME` personalizes the notification text

**Mailgun (default — does not require OpenClaw):**

Set in `.env`:

```
BRIEFBOT_NOTIFICATION_BACKEND=mailgun
MAILGUN_SENDING_API_KEY=<your sending key>
MAILGUN_DOMAIN=<your domain>
BRIEFBOT_EMAIL_TO=you@example.com
BRIEFBOT_EMAIL_FROM=briefbot@mg.yourdomain.com
DASHBOARD_BRIEFS_URL=https://your-machine.tail1234.ts.net/briefs
```

The email subject is `Briefbot: Daily Brief for YYYY-MM-DD` and the body includes the Tailscale dashboard link.
For Mailgun EU accounts add: `MAILGUN_API_BASE=https://api.eu.mailgun.net/v3`

**OpenClaw / Telegram (server deployments):**

```
BRIEFBOT_NOTIFICATION_BACKEND=openclaw
BRIEFBOT_TELEGRAM_TARGET=<chat id or @username>
OPENCLAW_BIN=openclaw
DASHBOARD_BRIEFS_URL=https://your-server/briefs
```

**Disable notifications:**

```
BRIEFBOT_NOTIFICATION_BACKEND=none
```

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

Default ports (high range to avoid conflicts with local dev):

- Backend: `59001`
- Frontend: `59000`
- Local dev (`LOCAL=1`): backend `59101`, frontend `59100`

### Persistent macOS Services (launchd)

The dashboard runs as macOS launchd services so it stays up across terminal sessions, crashes, and reboots. **This does not use OpenClaw.**

**First-time setup:**

```bash
# 1. Build the dashboard
make deploy-dashboard

# 2. Install and start the persistent services
make setup-dashboard-service
```

The two services installed are:
- `com.briefbot.dashboard-api` — uvicorn backend on port `59001`
- `com.briefbot.dashboard-frontend` — static file server on port `59000`

Both have `KeepAlive=true` and `RunAtLoad=true`, so they start on login and restart automatically if they crash.

**After code changes**, rebuild and the services pick up changes automatically:

```bash
make deploy-dashboard
```

**Stop services:**

```bash
make unload-dashboard-service
```

**Start services again:**

```bash
make setup-dashboard-service
```

**Check status:**

```bash
launchctl list | grep briefbot
```

**Tailscale Serve setup** (run once to expose the dashboard on your tailnet):

```bash
tailscale serve https / http://127.0.0.1:59000
tailscale serve https /api/ http://127.0.0.1:59001/api/
tailscale serve status
```

Then set `DASHBOARD_BRIEFS_URL` in `.env` to your Tailscale URL, e.g.:
`https://your-machine.tail1234.ts.net/briefs`

**Verify backend health:**

```bash
curl http://127.0.0.1:59001/api/health
curl http://127.0.0.1:59001/api/queries
curl http://127.0.0.1:59001/api/stories/sources
curl http://127.0.0.1:59001/api/stories
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

**Deploy (build + restart):**

```bash
make deploy-dashboard
```

This deploys the current local checkout and does not pull from Git by default. If launchd services are installed, deploy kicks them to reload the new build. If not, it manages processes via nohup/pid files.

To pull first:

```bash
make deploy-dashboard-pull
```

This script will:

- optionally run `git pull --ff-only` when using `make deploy-dashboard-pull`
- install Python and frontend dependencies
- build the dashboard with an embedded build SHA/timestamp
- restart services (via launchd if installed, otherwise nohup)
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
