# Briefbot API And Query Patterns

## Base URL

- Set `BRIEFBOT_API_BASE`
- Typical same-server value: `http://127.0.0.1:8000`

## Use `ask` for natural-language archive questions

Good for:

- "Were there any stories about NVIDIA last month?"
- "Are there any articles today that mention Jensen Huang?"
- "What was trending yesterday?"
- "Summarize Let There Be Claws..."

HTTP shape:

- `POST /api/query`
- body: `{"query":"..."}`

The backend:

- queries the archive through bounded tools
- can answer date-relative questions
- can summarize a specific article by title

## Use `stories` for deterministic filtering

HTTP shape:

- `POST /api/stories`

Body fields:

- `source_name`
- `from_date`
- `to_date`
- `limit`
- `cluster_id`
- `tags`
- `watch_hits`
- `order`

Good for:

- "show me arXiv stories from yesterday"
- "give me stories tagged security from last month"
- "return records mentioning a specific watch hit after applying exact filters"

## Metadata endpoints

- `GET /api/stories/sources`
- `GET /api/stories/clusters`
- `GET /api/stories/tags`
- `GET /api/stories/watch-hits`
- `GET /api/queries`
- `GET /api/queries/{id}`

## Date-window mapping

The helper script supports:

- `today`
- `yesterday`
- `last-week`
- `last-month`
- `this-month`

Mappings:

- `today`: from=today, to=today
- `yesterday`: from=yesterday, to=yesterday
- `last-week`: from=today-7d, to=today
- `last-month`: first to last day of previous calendar month
- `this-month`: first day of current month to today

## Suggested patterns

### Question answering

Use `ask`:

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py ask \
  --query "Were there any stories about NVIDIA last month?"
```

### Article summary by title

Use `summarize`:

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py summarize \
  --title "Let There Be Claws: An Early Social Network Analysis of AI Agents on Moltbook"
```

### Exact filtered records

Use `stories`:

```bash
python3 skills/briefbot-archive-query/scripts/briefbot_api.py stories \
  --window yesterday \
  --source arXiv \
  --limit 10
```
