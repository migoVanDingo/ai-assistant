# Briefbot

Briefbot is the local collection and synthesis pipeline for the Morning Brief app. It ingests technical news, papers, blogs, Hacker News items, and arXiv feeds into a SQLite archive, ranks and clusters those items, exports digest views, and writes daily Markdown briefs.

## Main Data Flow

1. `collect` reads `sources.yaml`, fetches configured sources, normalizes items, computes scores, applies watchlist matches, and upserts rows into `data/briefbot.db`.
2. `cluster` groups recent items into story clusters and writes `clusters`, `cluster_memberships`, and `cluster_events`.
3. `topics` computes topic profiles over a rolling window and writes `topic_profiles`.
4. `export` creates deterministic digest views under `data/daily_digest/`.
5. `write_daily_brief` composes `data/briefs/YYYY-MM-DD.daily.md` from exported views and optional LLM executive summaries.

The nightly shell workflow is `briefbot/nightly_briefbot.sh`. It loads `.env`, activates `.venv`, runs the pipeline, writes logs to `data/logs/nightly.YYYY-MM-DD.log`, and sends a notification if configured.

## Source Types

Configured source types:

- `rss`: RSS or Atom feed.
- `site`: site discovery plus feed fallback.
- `hn`: Hacker News feeds and keyword modes.
- `arxiv`: category or query-based arXiv ingestion.

Common source fields include `id`, `type`, `name`, `tags`, `weight`, `category`, `tier`, and optional `max_daily`.

## Ranking And Views

Items have a general `score` and, when applicable, an `score_opportunity` plus `opportunity_reason` and `opportunity_tags_json`.

Digest views:

- `balanced`: top links with category/source balance.
- `trends`: cluster-driven trending stories.
- `opportunities`: items with practical opportunity signals.
- `followups`: clusters with fresh follow-up activity.
- `topics`: rolling topic profiles.

Exports are written as both JSON and Markdown:

```text
data/daily_digest/YYYY-MM-DD.<view>.json
data/daily_digest/YYYY-MM-DD.<view>.md
```

## Daily Briefs

Daily briefs are Markdown files:

```text
data/briefs/YYYY-MM-DD.daily.md
```

Current layout:

- `What’s going on`
- `What’s trending`
- `Top Links`
- `Trends`
- `Opportunities`
- `Followups`
- `Today’s Moves`

The first two sections are LLM-generated executive summaries. The rest are deterministic renderings of exported data.

## LLM Summary Layers

There are two LLM paths:

- Item/article summaries use `briefbot.llm.summarize()`.
- Daily executive brief summaries use `briefbot.executive.build_exec_summaries()`.

Provider defaults:

- `BRIEFBOT_LLM_PROVIDER=anthropic`
- `BRIEFBOT_LLM_MODEL=claude-haiku-4-5-20251001`
- `BRIEFBOT_MODEL_FOR_SUMMARIES` can override executive-summary model selection.

The alias `claude-haiku`, `claude-haiku-latest`, `haiku`, or an empty Anthropic model resolves to `claude-haiku-4-5-20251001`, with older Haiku IDs attempted as fallback candidates.

Article text is fetched and cached in `data/article_cache/`. Item summaries are stored in the `summaries` table and mirrored to `data/summaries/`. Executive stage-1 article summaries are cached in `exec_summary_cache`.

## Important Commands

```bash
python -m briefbot collect
python -m briefbot cluster --date today --window-days 14
python -m briefbot topics --date today --window-days 30 --limit 50
python -m briefbot export --date today --view balanced --limit 50
python -m briefbot morning-brief --date today
./briefbot/nightly_briefbot.sh
make nightly-briefbot
```

Retrieval helpers:

```bash
python -m briefbot find --q "agentic eval framework" --date today --limit 20
python -m briefbot cite --item <item_id>
python -m briefbot get --item rank:balanced:3 --date today
python -m briefbot context --item rank:balanced:3 --date today --mode full
python -m briefbot summarize --item rank:balanced:3 --date today
```

Rank references accepted by retrieval commands:

- `rank:N`
- `rank:<view>:N`, for example `rank:balanced:12` or `rank:opportunities:3`

