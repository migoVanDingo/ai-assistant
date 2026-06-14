# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Use the project virtualenv interpreter directly — the bare `python` shim is not always on PATH:

```bash
.venv/bin/python -m briefbot run            # full pipeline: collect -> cluster -> exports
.venv/bin/python -m briefbot collect        # ingest sources into SQLite
.venv/bin/python -m briefbot cluster --date today --window-days 14
.venv/bin/python -m briefbot topics --date today
.venv/bin/python -m briefbot morning-brief --date today   # writes data/briefs/YYYY-MM-DD.daily.md
```

Tests (pytest, no config file; suite covers the `briefbot` pipeline only — there is no automated suite for the dashboard/agent):

```bash
.venv/bin/python -m pytest                              # all
.venv/bin/python -m pytest tests/test_cluster.py        # one file
.venv/bin/python -m pytest tests/test_resolve.py::test_name   # one test
```

Dashboard development:

```bash
.venv/bin/python -m uvicorn dashboard.backend.api:app --reload --port 8000   # backend
npm --prefix dashboard run dev      # frontend (Vite dev server; proxies /api -> :8000)
npm --prefix dashboard run build    # production bundle -> dashboard/dist
```

Deploy / run as the persistent local service (all run on this machine — none deploy to a remote host):

```bash
make deploy-dashboard         # the Tailscale-facing instance: base path /briefs/, ports 59000/59001
                              #   on loopback, relative /api URLs. Runs tailscale URL verification.
make deploy-dashboard-local   # localhost-only test instance: base /, ports 59100/59101,
                              #   absolute VITE_API_BASE_URL baked into the bundle.
make deploy-dashboard-pull    # git pull --ff-only first, then deploy
make nightly-briefbot         # run the nightly ingest/cluster/brief workflow once
```

`scripts/deploy_dashboard.sh` rebuilds `dashboard/dist` with the correct `VITE_*` env, then either restarts the launchd services `com.briefbot.dashboard-{api,frontend}` (if present) or spawns `nohup` processes. Anything LLM-driven needs `ANTHROPIC_API_KEY` (and optionally `OPENAI_API_KEY`) in `.env`.

## Architecture

The repo is two halves that meet at one SQLite database (`data/briefbot.db`):

**1. `briefbot/` — ingestion + radar + retrieval pipeline** (CLI: `python -m briefbot`). Flow is `collect -> cluster -> topics -> export -> morning-brief`. Key modules: `store.py` owns the SQLite schema and all pipeline writes (`items`, `clusters`, `cluster_memberships`, `topic_profiles`, and the `dashboard_*` tables); `resolve.py` is ranked search (`rank_items_for_query`); `article.py` fetches/extracts/caches article text; `executive.py` + `brief.py` do two-stage LLM synthesis for the daily brief. `nightly_briefbot.sh` chains the whole thing and sends a notification.

**2. `dashboard/` — FastAPI backend + React/Vite/MUI frontend** for browsing and querying the archive. The pipeline and the dashboard are decoupled: **`briefbot` never imports `dashboard`; `dashboard` imports `briefbot`** (`resolve`, `article`, `llm`, `store`, `normalize`). The DB is the integration boundary — the pipeline writes the corpus nightly, the dashboard reads it and owns its own `dashboard_*` tables (conversations, queries, story feedback, favorites).

### LLM / provider convention

`briefbot/llm.py` is the single provider abstraction — **raw `requests` to the Anthropic/OpenAI HTTP APIs, no SDK** (the SDK is intentionally not a dependency). `DEFAULT_ANTHROPIC_MODEL = claude-haiku-4-5-20251001`; `_normalize_model` / `_anthropic_model_candidates` resolve aliases and retry alternate model ids on 400/404. New LLM code should reuse this module's helpers rather than calling providers directly.

### Dashboard backend (`dashboard/backend/`)

- `dao.py` — the only read/write layer for the dashboard. Plain `sqlite3` + `Row` factory, **no ORM**. `get_dao()` in `api.py` opens a fresh `BriefbotDAO` per request and closes it in `finally`. `serialize_rows` / `_json_loads` are the JSON helpers.
- `api.py` — FastAPI app. **Every endpoint is registered twice** (`/api/...` and bare `/...`) to support subpath proxying; the frontend always calls `/api/...`. CORS allows localhost dev ports and `*.ts.net`.
- `agent/` — the `/ask` agent chat (see below).
- `llm_adapter.py` — the legacy one-shot tool-router behind `/api/query` + `dashboard_queries`. Superseded by the agent chat UI but still imported: the agent's `summarize_article` tool reuses `DashboardLLMAdapter._summarize_article`.

### Agent chat (`dashboard/backend/agent/`) — the `/ask` page

A from-scratch multi-turn tool-use loop over the raw Anthropic **streaming** HTTP API:

- `anthropic_stream.py` — SSE streaming client; yields text deltas and assembles `tool_use` blocks.
- `tools.py` — `Tool` base + `ToolRegistry`. Tools wrap DAO methods (search/trends/related/news/summarize) plus favorites management and conversation rename. `ToolContext` carries `dao`, `provider`, `model`, `conversation_id`; `ToolOutcome.events` lets a tool push extra SSE events (e.g. `rename_conversation` emits a `title` event mid-stream).
- `loop.py` — `run_chat_turn`: persists the user message, **rebuilds conversation history from the DB each turn**, runs the tool loop (`MAX_ITERATIONS = 12`), streams events, persists the assistant message, and auto-titles new conversations with one cheap Haiku call.

Served at `POST /api/conversations/{id}/messages` returning `text/event-stream`. **Critical pattern:** the endpoint wraps `run_chat_turn` (a *synchronous* generator) in Starlette `StreamingResponse`. Starlette iterates sync generators in a threadpool, which is why the blocking `requests` calls and the per-thread sqlite connection are safe — **the DAO must be created inside the generator** so the connection lives on the threadpool thread. SSE event `type`s: `token`, `tool_start`, `tool_end`, `title`, `done`, `error`. Conversations persist in `dashboard_conversations` + `dashboard_conversation_messages` (rename via `PATCH /api/conversations/{id}`).

### Frontend (`dashboard/src/`)

React 18 + Vite + MUI v6 + react-router. Routes: `/` BriefPage, `/ask` ChatPage, `/stories` StoriesPage, `/favorites` FavoritesPage. `services/api.js` is the single fetch wrapper; `api.streamChatMessage` consumes the chat SSE via `fetch` + a `ReadableStream` reader. The API origin and base path are baked at build time from `VITE_API_BASE_URL` / `VITE_APP_BASE` (set by the deploy script per target). **`dashboard/dist` is committed and is what the static server serves in production** — don't hand-edit it; let the deploy script rebuild it.

## Docs

`docs/` has deeper integration notes: `briefbot.md` (pipeline), `dashboard.md` (API + runtime), `database.md` (schema + read-only access for other apps), `agent-harness-integration.md`.
