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

`VITE_API_BASE_URL` is optional and is only honored when it is a full origin such as:

- `http://127.0.0.1:8000`
- `https://your-node.ts.net`

`VITE_ALLOWED_HOSTS` is optional and can be set to a comma-separated list of dev-server hostnames, for example:

- `VITE_ALLOWED_HOSTS=your-node.ts.net`
- `VITE_ALLOWED_HOSTS=your-node.ts.net,localhost`

Do not set:

- `VITE_API_BASE_URL=/briefs`
- `VITE_API_BASE_URL=/briefs/`
- any other path-only value

If unset, the frontend defaults to same-origin root-relative API calls such as `/api/metrics`.

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

- `/briefs` -> frontend static server
- `/api` -> FastAPI backend

Tailscale Serve can forward the mounted request with the prefix stripped before it reaches the upstream process. The backend therefore supports both `/api/*` and stripped aliases like `/metrics`, `/briefs`, and `/query`, and logs `scope.path` plus forwarded headers so you can verify what actually arrived at uvicorn.

Run frontend in development:

```bash
cd dashboard
VITE_APP_BASE=/briefs/ npm run dev -- --host 127.0.0.1 --port 5173
```

Run backend:

```bash
uvicorn dashboard.backend.api:app --reload --host 127.0.0.1 --port 8000
```

Recommended production deploy:

```bash
make deploy-dashboard
```

This deploys the current local checkout and does not pull from Git by default.

If you want to update from the remote first, use:

```bash
make deploy-dashboard-pull
```

This builds the frontend into `dashboard/dist`, embeds the build SHA/timestamp, starts:

- FastAPI on `127.0.0.1:8000`
- the included static SPA server on `127.0.0.1:4173`

Git update behavior:

- `make deploy-dashboard`: deploy current local files only
- `make deploy-dashboard-pull`: run `git pull --ff-only` first, then deploy
- shell equivalent: `DEPLOY_PULL=1 ./scripts/deploy_dashboard.sh`

Recommended Tailscale Serve config shape:

```text
/briefs  -> http://127.0.0.1:4173
/api     -> http://127.0.0.1:8000
```

The deploy script verifies:

- local `http://127.0.0.1:8000/api/health`
- local `http://127.0.0.1:8000/api/metrics`
- the served HTML references the newest hashed bundle
- the bundle contains `/api/metrics`, `/api/briefs`, and `/api/query`
- the public Tailscale `/api/metrics` endpoint returns `200` when a tailnet URL can be resolved

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
