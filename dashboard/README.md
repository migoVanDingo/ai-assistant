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

## Backend

```bash
uvicorn dashboard.backend.api:app --reload --host 0.0.0.0 --port 8000
```

Environment variables respected:

- `BRIEFBOT_DB_PATH`
- `BRIEFBOT_BRIEF_DIR`
- `BRIEFBOT_LLM_PROVIDER`
- `BRIEFBOT_LLM_MODEL`
- `BRIEFBOT_MODEL_FOR_SUMMARIES`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
