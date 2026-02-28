# Dashboard

React + MUI dashboard for reading daily briefs and querying the briefbot database through a Python API.

## Frontend

```bash
cd dashboard
npm install
npm run dev
```

Vite dev server defaults to `http://localhost:5173` and proxies `/api` to `http://localhost:8000`.

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
