# Dashboard

The dashboard is a React + MUI frontend with a FastAPI backend over the Briefbot SQLite archive.

## Runtime Components

- Frontend source: `dashboard/src/`
- Frontend build output: `dashboard/dist/`
- Backend API: `dashboard/backend/api.py`
- Backend DAO: `dashboard/backend/dao.py`
- Ask/LLM adapter: `dashboard/backend/llm_adapter.py`
- Static frontend server: `dashboard/backend/static_server.py`

Default ports:

- Backend: `http://127.0.0.1:59001`
- Frontend: `http://127.0.0.1:59000`
- Local deploy mode: backend `59101`, frontend `59100`

Tailscale serve is expected to expose frontend at `/briefs` and backend under `/api`.

## Pages

- `/`: morning brief reader, latest metrics, and brief archive.
- `/ask`: Ask Briefbot, backed by `POST /api/query`.
- `/stories`: deterministic story browser with source/date/search/cluster/tag/watch-hit filters.

## Backend Configuration

At startup, `dashboard/backend/api.py` loads `.env` through `python-dotenv` when available.

Important environment variables:

- `BRIEFBOT_DB_PATH`: SQLite database path, default `data/briefbot.db`.
- `BRIEFBOT_BRIEF_DIR`: daily brief directory, default `data/briefs`.
- `BRIEFBOT_DASHBOARD_BRIEF_DIR`: dashboard-specific brief directory override.
- `BRIEFBOT_LOG_DIR`: logs directory, default `data/logs`.
- `BRIEFBOT_LLM_PROVIDER`: default `/api/query` provider, usually `anthropic`.
- `BRIEFBOT_LLM_MODEL`: default model.
- `BRIEFBOT_MODEL_FOR_SUMMARIES`: model override used before `BRIEFBOT_LLM_MODEL` in `/api/query`.
- `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`: provider credentials.

## API Endpoints

All primary endpoints are prefixed with `/api`. Several also have non-prefixed aliases for local use.

Briefs and metrics:

```http
GET /api/health
GET /api/briefs
GET /api/briefs/{date}
GET /api/metrics
```

Ask/query:

```http
POST /api/query
GET /api/queries?days=14&limit=20
GET /api/queries/{query_id}
```

`POST /api/query` request:

```json
{
  "query": "what is trending in agent frameworks this week?",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

`provider` and `model` are optional. Response shape:

```json
{
  "query": "...",
  "tool": "search_items",
  "arguments": {"query": "...", "days": 30, "limit": 20},
  "answer": "Markdown response",
  "data": {},
  "history_id": "uuid",
  "created_at": "ISO timestamp"
}
```

Stories:

```http
GET  /api/stories/sources
GET  /api/stories/clusters
GET  /api/stories/tags
GET  /api/stories/watch-hits
GET  /api/stories/sections?section_limit=12
GET  /api/stories?source_name=...&search=...&limit=20
POST /api/stories
POST /api/stories/feedback
POST /api/stories/resolve-links
```

`POST /api/stories` request:

```json
{
  "source_name": "Hacker News New",
  "from_date": "2026-04-20",
  "to_date": "2026-04-25",
  "search": "agents",
  "limit": 20,
  "cluster_id": null,
  "tags": ["ai"],
  "watch_hits": [],
  "order": "desc"
}
```

Favorites:

```http
GET    /api/favorites/folders
POST   /api/favorites/folders
GET    /api/favorites/items
POST   /api/favorites/items
DELETE /api/favorites/items
```

Jobs and imports:

```http
GET  /api/jobs/nightly
POST /api/jobs/nightly
POST /api/arxiv/import
```

Nightly job modes:

- `standard`
- `arxiv_backfill_2y`

## Deploy And Restart

Use:

```bash
make deploy-dashboard
```

This runs `scripts/deploy_dashboard.sh`, which:

- installs Python dependencies into `.venv`
- installs dashboard npm dependencies
- builds `dashboard/dist`
- embeds build SHA/time into the frontend bundle
- restarts launchd services when installed, otherwise manages nohup processes and PID files
- verifies local backend endpoints and served frontend HTML
- verifies public Tailscale endpoints when discoverable

Persistent macOS services:

- `com.briefbot.dashboard-api`
- `com.briefbot.dashboard-frontend`

Install/start:

```bash
make setup-dashboard-service
```

Stop:

```bash
make unload-dashboard-service
```

## Frontend API Base Behavior

The frontend calls relative `/api/*` routes by default. If `VITE_API_BASE_URL` is set to a full origin such as `http://localhost:59101`, the frontend prepends that origin.

For Tailscale subpath hosting, keep frontend assets under `/briefs/` and backend routes under `/api/*`; do not route API calls through `/briefs/api/*`.

