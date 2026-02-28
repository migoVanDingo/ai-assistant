# Dashboard

React + MUI dashboard for reading daily briefs and querying the briefbot database through a Python API.

## Frontend

```bash
cd dashboard
npm install
npm run dev
```

Vite dev server defaults to `http://localhost:5173` and proxies `/api` to `http://localhost:8000`.

Base-path hosting:

- local root hosting:
  - `VITE_APP_BASE=/ npm run dev`
- subpath hosting under `/briefs/`:
  - `VITE_APP_BASE=/briefs/ npm run dev -- --host 0.0.0.0`

React Router uses `import.meta.env.BASE_URL` as its basename, so these paths should work when the hosting layer rewrites requests to the SPA entrypoint:

- `/briefs`
- `/briefs/ask`
- refresh on `/briefs/ask`

The frontend API helper intentionally uses absolute `/api/*` paths. For local dev that works through the Vite proxy. For Tailscale Serve, route `/api` directly to the backend rather than the frontend.

## Backend

```bash
uvicorn dashboard.backend.api:app --reload --host 0.0.0.0 --port 8000
```

Verification:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/briefs
curl http://127.0.0.1:8000/api/metrics
```

Environment variables respected:

- `BRIEFBOT_DB_PATH`
- `BRIEFBOT_BRIEF_DIR`
- `BRIEFBOT_LLM_PROVIDER`
- `BRIEFBOT_LLM_MODEL`
- `BRIEFBOT_MODEL_FOR_SUMMARIES`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

## Tailscale Serve

Recommended layout when hosting the dashboard at `/briefs`:

- `/briefs` -> frontend Vite/dev server
- `/api` -> FastAPI backend

Run frontend:

```bash
cd dashboard
VITE_APP_BASE=/briefs/ npm run dev -- --host 127.0.0.1 --port 5173
```

Run backend:

```bash
uvicorn dashboard.backend.api:app --reload --host 127.0.0.1 --port 8000
```

Recommended Tailscale Serve config shape:

```text
/briefs  -> http://127.0.0.1:5173
/api     -> http://127.0.0.1:8000
```

If you configure SPA fallback for the frontend mount, verify:

- `https://<node>.ts.net/briefs`
- `https://<node>.ts.net/briefs/ask`
- refresh on `https://<node>.ts.net/briefs/ask`

The backend CORS policy allows:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:4173`
- `http://127.0.0.1:4173`
- any `https://*.ts.net` origin
