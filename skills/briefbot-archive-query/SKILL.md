---
name: briefbot-archive-query
description: Query a deployed Briefbot archive over local HTTP when you need to search stories, ask date-based questions like "yesterday" or "last month", summarize a specific article by title, inspect trends/topics, or browse deterministic story filters from the Briefbot backend running on the same server as OpenClaw.
---

# Briefbot Archive Query

Use the local Briefbot backend over HTTP, not direct SQLite access.

## Quick Start

- Set `BRIEFBOT_API_BASE`, usually `http://127.0.0.1:8000`
- For natural-language archive questions, run `scripts/briefbot_api.py ask --query "..."`
- For article summaries by title, run `scripts/briefbot_api.py summarize --title "..."`
- For deterministic filtered browsing, run `scripts/briefbot_api.py stories ...`
- Read `references/api-and-query-patterns.md` if you need endpoint details or query examples

## Workflow

1. Decide whether the request is conversational or deterministic.
2. Use `ask` for:
   - "Were there any stories about NVIDIA last month?"
   - "Are there any articles today that mention Jensen Huang?"
   - "Summarize Let There Be Claws..."
   - "What was trending yesterday?"
3. Use `stories` for:
   - exact source/date/tag/watch-hit browsing
   - reproducible filtered lists
   - returning raw story records rather than a synthesized answer
4. Prefer article summarization over search results when the user asks to summarize a specific article.

## Commands

### Ask the archive

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py ask \
  --query "Were there any stories about NVIDIA last month?"
```

### Summarize an article by title

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py summarize \
  --title "Let There Be Claws: An Early Social Network Analysis of AI Agents on Moltbook"
```

### Deterministic stories query

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py stories \
  --window last-month \
  --limit 20 \
  --order desc
```

### Deterministic stories query with source/tag/watch hit

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py stories \
  --window yesterday \
  --source "arXiv" \
  --watch-hit "Jensen Huang" \
  --tag ai \
  --limit 10
```

## Date Windows

Supported relative windows in the helper script:

- `today`
- `yesterday`
- `last-week`
- `last-month`
- `this-month`

Use explicit `YYYY-MM-DD` dates when the user gives exact dates.

## Response Guidance

- If the user asks for stories/records, return the grounded records.
- If the user asks a question, use the `ask` endpoint and return the backend answer.
- If the user asks to summarize an article, use `summarize`; do not stop at record matching.
- When the backend returns markdown, preserve it.

## Resources

### scripts/

- `briefbot_api.py`: helper for calling the local Briefbot backend over HTTP

### references/

- `api-and-query-patterns.md`: endpoint summary, date-window handling, and example prompts
