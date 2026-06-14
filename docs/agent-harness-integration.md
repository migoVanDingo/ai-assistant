# Agent Harness Integration

This document is for an external agent harness that wants to use Briefbot data and integrate with the dashboard `/ask` page.

## Current `/ask` Architecture

The `/ask` page calls:

```http
POST /api/query
```

The FastAPI endpoint creates a `BriefbotDAO`, constructs a `DashboardLLMAdapter`, executes `adapter.answer_query(query)`, records the response in `dashboard_queries`, and returns Markdown plus execution details.

Current request shape:

```json
{
  "query": "summarize the DeepSeek V4 story",
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

`provider` and `model` are optional. Response shape:

```json
{
  "query": "summarize the DeepSeek V4 story",
  "tool": "summarize_article",
  "arguments": {"query": "DeepSeek V4 story"},
  "answer": "Markdown answer",
  "data": {},
  "history_id": "uuid",
  "created_at": "2026-04-26T12:00:00+00:00"
}
```

The frontend then renders `answer` as Markdown and updates the URL to:

```text
/ask?queryId=<history_id>
```

Selecting a saved query calls `GET /api/queries/{query_id}` and replays the stored Markdown response without another LLM call.

## Current LLM Adapter Flow

`dashboard/backend/llm_adapter.py` has a bounded tool router:

1. Ask an LLM to select one tool and arguments.
2. Fall back to deterministic routing for obvious queries.
3. Execute the selected DAO-backed tool.
4. For some result shapes, render deterministic Markdown directly.
5. Otherwise ask the LLM to synthesize a concise answer grounded in the tool result.

Available tools:

- `summarize_article`: find best matching item, fetch article text, summarize it.
- `get_trending_topics`: read `topic_profiles`.
- `get_trend_clusters`: read `clusters`.
- `search_items`: ranked search over recent `items`.
- `get_related_stories`: find a matching item and its cluster neighbors.
- `get_news_about`: search recent items and matching clusters for an entity/topic.

The LLM provider abstraction is `briefbot.llm.generate_text()`. It supports:

- Anthropic Messages API via `ANTHROPIC_API_KEY`.
- OpenAI chat completions via `OPENAI_API_KEY`.

Default Anthropic model is `claude-haiku-4-5-20251001`.

## Integration Options

### Option A: Harness Calls Existing `/api/query`

This is the lowest-friction approach. The harness submits user text and receives a Markdown response plus structured tool data.

Example:

```bash
curl -sS http://127.0.0.1:59001/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"what agent stories are trending this week?"}'
```

Pros:

- no direct DB coupling
- records query history automatically
- matches current `/ask` UI behavior

Cons:

- harness cannot control multi-step plans beyond the natural language query
- the current endpoint only accepts `query`, `provider`, and `model`

### Option B: Add A Harness Proxy Endpoint To This Backend

Add a new endpoint such as:

```http
POST /api/harness/query
```

Payload idea:

```json
{
  "query": "compare the top agent framework stories",
  "session_id": "external-session-id",
  "context": {
    "user_id": "optional",
    "selected_item_ids": ["..."],
    "mode": "deep_research"
  }
}
```

The endpoint can:

1. Resolve Briefbot context with `BriefbotDAO`.
2. Call the external harness webserver.
3. Store the harness Markdown answer in `dashboard_queries`.
4. Return the same shape as `/api/query` so the existing `/ask` page can render it.

Recommended response shape:

```json
{
  "query": "...",
  "tool": "external_harness",
  "arguments": {"session_id": "..."},
  "answer": "Markdown answer from harness",
  "data": {
    "harness_trace_id": "...",
    "citations": []
  },
  "history_id": "...",
  "created_at": "..."
}
```

This preserves the current frontend contract.

### Option C: Let The Harness Read SQLite Directly

Use read-only SQLite access from the harness process. See `docs/database.md`.

This is best when the harness needs complex local retrieval, custom ranking, or multi-step plans independent of the dashboard backend.

The harness can still write a final answer back through a small Briefbot endpoint, or you can add a table such as `agent_harness_runs` and have the dashboard read from it.

### Option D: Replace `/api/query` Internals With Harness Dispatch

Keep the frontend unchanged and modify `query_llm()` in `dashboard/backend/api.py`:

- if `BRIEFBOT_AGENT_HARNESS_URL` is set, send the query to the harness;
- otherwise use `DashboardLLMAdapter`.

This makes the harness the primary Ask engine while retaining fallback behavior.

Example environment:

```text
BRIEFBOT_AGENT_HARNESS_URL=http://127.0.0.1:59200/query
BRIEFBOT_AGENT_HARNESS_TIMEOUT_S=120
```

Suggested harness request:

```json
{
  "query": "what agent stories are trending this week?",
  "briefbot": {
    "db_path": "data/briefbot.db",
    "api_base_url": "http://127.0.0.1:59001/api"
  }
}
```

Suggested harness response:

```json
{
  "answer_md": "Markdown answer",
  "tool_name": "agent_harness",
  "tool_args": {},
  "tool_result": {
    "citations": [
      {"item_id": "...", "title": "...", "url": "..."}
    ]
  },
  "error": null
}
```

Map that response into the current `/api/query` response and `dashboard_queries` row.

## Recommended API Contract For Harness Integration

If the other app is an agent harness running in a separate process or webserver, prefer a stable HTTP boundary:

```http
POST http://127.0.0.1:59200/query
Content-Type: application/json
```

Request:

```json
{
  "query": "user question",
  "session_id": "optional stable session id",
  "briefbot_context": {
    "api_base_url": "http://127.0.0.1:59001/api",
    "db_path": "/absolute/path/to/data/briefbot.db",
    "selected_item_ids": [],
    "selected_cluster_ids": []
  }
}
```

Response:

```json
{
  "answer_md": "Markdown answer",
  "citations": [
    {"item_id": "abc", "title": "Story title", "url": "https://example.com"}
  ],
  "artifacts": {},
  "trace_id": "optional",
  "error": null
}
```

Briefbot should store:

- `answer_md` in `dashboard_queries.llm_response_md`
- `agent_harness` in `dashboard_queries.tool_name`
- request metadata in `dashboard_queries.tool_args_json`
- citations/artifacts/trace ID in `dashboard_queries.tool_result_json`

## Useful Briefbot Context Endpoints For A Harness

Use these instead of direct SQL when possible:

```http
GET  /api/metrics
GET  /api/stories?search=agents&limit=20
POST /api/stories
GET  /api/stories/sections?section_limit=12
GET  /api/stories/clusters
GET  /api/stories/tags
GET  /api/briefs
GET  /api/briefs/{date}
```

For direct SQLite retrieval, see `docs/database.md`.

## Frontend Changes Needed For Deeper Harness Features

The current `/ask` page only submits `{query}` plus optional provider/model if the caller supplies them. It can render any Markdown response returned as `answer`.

To expose harness-specific features in the UI, add fields to `QueryRequest` and `api.query()`:

- `mode`: e.g. `quick`, `deep`, `research`.
- `session_id`: external harness session.
- `selected_item_ids`: item context from Stories or Brief pages.
- `selected_cluster_ids`: cluster context.
- `stream`: future streaming mode flag.

The safest first integration is non-streaming. Add streaming later with Server-Sent Events or WebSockets if the harness needs progress updates.

## Guardrails

- Keep `/api/query` response backward-compatible: always return `answer` Markdown and `history_id`.
- Use read-only DB connections in the harness unless there is a deliberate write path.
- Keep harness-owned state in harness tables or a separate DB.
- Include `item_id`, `cluster_id`, and URLs in harness citations so answers can deep-link back into Briefbot.
- Treat Briefbot source text as untrusted web content; prompt the harness to ground answers in retrieved rows and cite sources.

