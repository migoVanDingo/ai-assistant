"""Command-line orchestration for collect/export/radar and retrieval workflows.

Subcommands:
- collect, cluster, export, run, morning-brief
- find, cite, get, context, summarize
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

from .article import get_article_for_item
from .brief import write_daily_brief
from .cluster import cluster_items_for_window
from .config import load_config
from .export import export_daily_digest
from .llm import summarize as llm_summarize
from .resolve import format_citation, rank_items_for_query, resolve_date, resolve_item_reference
from .score import compute_score
from .store import Store
from .topics import compute_topic_profiles
from .watchlist import load_watchlist, match_watchlist


def _parse_csv_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _default_provider() -> str:
    return os.getenv("BRIEFBOT_LLM_PROVIDER", "anthropic").strip() or "anthropic"


def _default_model() -> str:
    return os.getenv("BRIEFBOT_LLM_MODEL", "claude-haiku-latest").strip() or "claude-haiku-latest"


def _default_cache_dir() -> str:
    return os.getenv("BRIEFBOT_CACHE_DIR", "data/article_cache").strip() or "data/article_cache"


def _default_summary_dir() -> str:
    return os.getenv("BRIEFBOT_SUMMARY_DIR", "data/summaries").strip() or "data/summaries"


def _rss_fallback_collect(
    source: dict[str, Any],
    store: Store,
    session: requests.Session,
) -> list[dict[str, Any]]:
    from .discover import discover_site_feeds
    from .fetch import fetch_rss_feed, source_homepage

    fallback_home = source_homepage(source)
    if not fallback_home:
        return []

    cached = store.get_discovered_feeds(fallback_home, max_age_days=7)
    feed_urls = cached
    if feed_urls is None:
        feed_urls = discover_site_feeds(
            fallback_home,
            session=session,
            verify_ssl=bool(source.get("verify_ssl", True)),
        )
        store.set_discovered_feeds(fallback_home, feed_urls)

    items: list[dict[str, Any]] = []
    for feed_url in feed_urls:
        try:
            feed_items, _ = fetch_rss_feed(source, feed_url, store=store, session=session)
            items.extend(feed_items)
        except Exception as exc:
            print(f"[{source['id']}] fallback feed error {feed_url}: {exc}")
    return items


def _resolve_item(store: Store, item_ref: str, date_value: str) -> dict[str, Any]:
    date_str = resolve_date(date_value)
    item_id = resolve_item_reference(store=store, item_ref=item_ref, date_str=date_str)
    item = store.get_item_by_id(item_id)
    if not item:
        raise ValueError(f"Item not found: {item_id}")
    return item


def _ensure_summary(
    store: Store,
    item: dict[str, Any],
    provider: str,
    model: str,
    cache_dir: str,
    summary_dir: str,
    force: bool = False,
    max_chars: int = 12000,
    allow_metadata_only: bool = True,
) -> tuple[str, dict[str, Any]]:
    item_id = item["item_id"]

    article_meta: dict[str, Any] | None = None
    text_for_summary = ""
    content_hash = None

    if allow_metadata_only and (item.get("source_category") == "papers") and item.get("summary"):
        text_for_summary = item.get("summary") or ""
        content_hash = hashlib.sha256(text_for_summary.encode("utf-8")).hexdigest()
    else:
        article_meta = get_article_for_item(
            item=item,
            cache_dir=cache_dir,
            force=False,
            max_chars=max_chars,
        )
        text_for_summary = article_meta.get("llm_text") or article_meta.get("text") or ""
        content_hash = article_meta.get("content_hash")

    existing = store.get_summary(item_id=item_id, provider=provider, model=model)
    if existing and not force and existing.get("content_hash") == content_hash:
        return str(existing.get("summary_md") or ""), (article_meta or {})

    if not text_for_summary.strip():
        text_for_summary = item.get("summary") or item.get("title") or ""

    metadata = {
        "title": item.get("title"),
        "source_name": item.get("source_name"),
        "source_id": item.get("source_id"),
        "published_at": item.get("published_at"),
        "url": item.get("canonical_url") or item.get("url"),
        "tags": item.get("tags") or [],
        "source_category": item.get("source_category"),
    }

    summary_md = llm_summarize(
        text=text_for_summary[:max_chars],
        metadata=metadata,
        provider=provider,
        model=model,
        max_words=400,
    )
    store.upsert_summary(
        item_id=item_id,
        provider=provider,
        model=model,
        summary_md=summary_md,
        content_hash=content_hash,
    )

    summary_dir_path = Path(summary_dir)
    summary_dir_path.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "-", model)
    out_path = summary_dir_path / f"{item_id}.{provider}.{safe_model}.md"
    out_path.write_text(summary_md, encoding="utf-8")

    return summary_md, (article_meta or {})


def run_collect(args: argparse.Namespace) -> int:
    from .discover import discover_site_feeds
    from .fetch import FetchError, fetch_arxiv_source, fetch_hn_source, fetch_rss_feed
    from .opportunity import compute_opportunity

    config = load_config(args.config)
    watchlist = load_watchlist(args.watchlist)
    store = Store(args.db)
    session = requests.Session()

    total_sources = 0
    total_inserted = 0
    total_duplicates = 0
    total_errors = 0

    print(f"Collecting from {len(config['sources'])} sources...")
    for source in config["sources"]:
        total_sources += 1
        sid = source["id"]
        sname = source.get("name", sid)
        inserted = 0
        duplicates = 0
        status = "ok"

        try:
            source_items: list[dict[str, Any]] = []

            if source["type"] == "rss":
                if "url" not in source:
                    raise FetchError(f"rss source {sid} missing url")
                try:
                    feed_items, _ = fetch_rss_feed(source, source["url"], store=store, session=session)
                    source_items.extend(feed_items)
                except FetchError as exc:
                    if exc.status_code in {404, 410}:
                        source_items.extend(_rss_fallback_collect(source, store=store, session=session))
                    else:
                        raise

            elif source["type"] == "site":
                if "url" not in source:
                    raise FetchError(f"site source {sid} missing url")
                feed_urls = None if args.refresh_discovery else store.get_discovered_feeds(source["url"], max_age_days=7)
                if not feed_urls:
                    feed_urls = discover_site_feeds(
                        source["url"],
                        session=session,
                        verify_ssl=bool(source.get("verify_ssl", True)),
                    )
                    store.set_discovered_feeds(source["url"], feed_urls)

                for feed_url in feed_urls:
                    try:
                        feed_items, _ = fetch_rss_feed(source, feed_url, store=store, session=session)
                        source_items.extend(feed_items)
                    except Exception as exc:
                        print(f"[{sid}] feed error {feed_url}: {exc}")

                if not feed_urls:
                    status = "no_feeds_discovered"
                elif not source_items:
                    status = "no_entries_returned"

            elif source["type"] == "hn":
                source_items.extend(fetch_hn_source(source, session=session))

            elif source["type"] == "arxiv":
                source_items.extend(fetch_arxiv_source(source, session=session))

            else:
                raise FetchError(f"Unsupported source type: {source['type']}")

            source_weight = float(source.get("weight", 1.0))
            for item in source_items:
                item["watch_hits"] = match_watchlist(item.get("title"), item.get("summary"), watchlist)
                if item["watch_hits"]:
                    raw = dict(item.get("raw") or {})
                    raw["watch_hits"] = item["watch_hits"]
                    item["raw"] = raw
                item["score"] = compute_score(item, source_weight=source_weight)
                opp = compute_opportunity(item)
                item.update(
                    {
                        "score_opportunity": opp.get("score_opportunity"),
                        "opportunity_reason": opp.get("opportunity_reason"),
                        "opportunity_tags": opp.get("opportunity_tags", []),
                    }
                )
                if opp.get("components"):
                    raw = dict(item.get("raw") or {})
                    raw["opportunity_components"] = opp["components"]
                    item["raw"] = raw
                result = store.upsert_item(item, dry_run=args.dry_run)
                if result.inserted:
                    inserted += 1
                if result.duplicate:
                    duplicates += 1

            total_inserted += inserted
            total_duplicates += duplicates

        except Exception as exc:
            status = f"error: {exc}"
            total_errors += 1

        print(f"[{sid}] {sname}: inserted={inserted} duplicate={duplicates} status={status}")

    store.close()
    print(
        f"Summary: sources_processed={total_sources} new_items={total_inserted} "
        f"duplicates={total_duplicates} errors={total_errors} dry_run={args.dry_run}"
    )
    return 0 if total_errors == 0 else 1


def run_cluster(args: argparse.Namespace) -> int:
    cluster_date = resolve_date(args.date)
    store = Store(args.db)
    stats = cluster_items_for_window(store=store, date_str=cluster_date, window_days=args.window_days)
    store.close()
    print(
        f"Clustered window ending {cluster_date}: items={stats['items']} "
        f"clusters={stats['clusters']} window_days={args.window_days}"
    )
    return 0


def run_export(args: argparse.Namespace) -> int:
    export_date = resolve_date(args.date)
    include_tags = _parse_csv_arg(args.include_tags)
    exclude_tags = _parse_csv_arg(args.exclude_tags)

    store = Store(args.db)
    json_path, md_path, count = export_daily_digest(
        store=store,
        date_str=export_date,
        limit=args.limit,
        view=args.view,
        config_path=args.config,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )
    store.close()

    print(f"Exported {count} items")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    if args.view in {"trends", "followups"} and count == 0:
        print("No clustered data found for this view. Run `python -m briefbot cluster --date ...` first.")
    return 0


def run_topics(args: argparse.Namespace) -> int:
    topics_date = resolve_date(args.date)
    store = Store(args.db)
    stats = compute_topic_profiles(store=store, date_str=topics_date, window_days=args.window_days)
    store.close()
    print(
        f"Computed topic profiles for {topics_date}: items={stats['items']} "
        f"topics={stats['topics']} window_days={args.window_days}"
    )

    export_args = argparse.Namespace(
        db=args.db,
        config=args.config,
        date=topics_date,
        limit=args.limit,
        view="topics",
        include_tags="",
        exclude_tags="",
    )
    return run_export(export_args)


def run_find(args: argparse.Namespace) -> int:
    date_str = resolve_date(args.date) if args.date else None
    include_tags = _parse_csv_arg(args.include_tags)
    exclude_tags = _parse_csv_arg(args.exclude_tags)

    store = Store(args.db)
    items = store.search_items(
        query=args.q,
        date_str=date_str,
        limit=args.limit,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )
    ranked = rank_items_for_query(args.q, items)[: args.limit]
    store.close()

    if args.json:
        print(json.dumps({"query": args.q, "count": len(ranked), "items": ranked}, indent=2, ensure_ascii=True))
        return 0

    for idx, item in enumerate(ranked, start=1):
        tags = ",".join(item.get("tags") or [])
        print(
            f"{idx}. {item.get('item_id')} | {item.get('title')}\n"
            f"   source={item.get('source_name')} published={item.get('published_at')} "
            f"score={item.get('score')} qscore={item.get('query_score')} tags=[{tags}]\n"
            f"   {item.get('url')}"
        )
    return 0


def run_cite(args: argparse.Namespace) -> int:
    store = Store(args.db)
    item = store.get_item_by_id(args.item)
    store.close()
    if not item:
        print(f"Item not found: {args.item}")
        return 1

    citation = format_citation(item, fmt=args.format)
    if args.format == "json":
        print(json.dumps(citation, indent=2, ensure_ascii=True))
    else:
        print(citation)
    return 0


def run_get(args: argparse.Namespace) -> int:
    date_value = args.date or "today"
    store = Store(args.db)
    try:
        item = _resolve_item(store, args.item, date_value=date_value)
        result = get_article_for_item(
            item=item,
            cache_dir=args.cache_dir,
            force=args.force,
            max_bytes=args.max_bytes,
            max_chars=args.max_chars,
        )
    finally:
        store.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0

    print(f"Cached text: {result['path']}")
    print(f"LLM text: {result['llm_path']}")
    print(f"Content hash: {result['content_hash']}")
    print(f"Snippet: {result['snippet']}")
    return 0


def run_summarize(args: argparse.Namespace) -> int:
    date_value = args.date or "today"
    provider = args.provider or _default_provider()
    model = args.model or _default_model()

    store = Store(args.db)
    try:
        item = _resolve_item(store, args.item, date_value=date_value)
        summary_md, article_meta = _ensure_summary(
            store=store,
            item=item,
            provider=provider,
            model=model,
            cache_dir=args.cache_dir,
            summary_dir=args.summary_dir,
            force=args.force,
            max_chars=args.max_chars,
        )
    except Exception as exc:
        store.close()
        print(f"Summarization failed ({provider}/{model}): {exc}")
        if provider == "anthropic":
            print("Tip: try `--provider openai --model gpt-4o-mini` to verify end-to-end path.")
        return 1

    store.close()
    if args.json:
        print(
            json.dumps(
                {
                    "item_id": item.get("item_id"),
                    "provider": provider,
                    "model": model,
                    "summary_md": summary_md,
                    "article": article_meta,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    print(summary_md)
    return 0


def run_context(args: argparse.Namespace) -> int:
    date_value = args.date or "today"
    provider = args.provider or _default_provider()
    model = args.model or _default_model()

    store = Store(args.db)
    try:
        item = _resolve_item(store, args.item, date_value=date_value)
        citation_md = str(format_citation(item, fmt="md"))

        if args.mode == "summary":
            summary_text = item.get("summary") or ""
            if not summary_text.strip():
                cached = store.get_summary(item_id=item["item_id"], provider=provider, model=model)
                if cached:
                    summary_text = cached.get("summary_md") or ""
            if not summary_text.strip():
                try:
                    summary_text, _ = _ensure_summary(
                        store=store,
                        item=item,
                        provider=provider,
                        model=model,
                        cache_dir=args.cache_dir,
                        summary_dir=args.summary_dir,
                        force=False,
                        max_chars=args.max_chars,
                    )
                except Exception as exc:
                    summary_text = f"Summary unavailable: {exc}"

            payload = f"{citation_md}\n\n### Summary\n{summary_text}"
        else:
            article = get_article_for_item(
                item=item,
                cache_dir=args.cache_dir,
                force=args.force,
                max_bytes=args.max_bytes,
                max_chars=args.max_chars,
            )
            try:
                summary_text, _ = _ensure_summary(
                    store=store,
                    item=item,
                    provider=provider,
                    model=model,
                    cache_dir=args.cache_dir,
                    summary_dir=args.summary_dir,
                    force=False,
                    max_chars=args.max_chars,
                )
            except Exception as exc:
                summary_text = f"Summary unavailable: {exc}"

            full_text = article.get("llm_text") or article.get("text") or ""
            payload = f"{citation_md}\n\n### Summary\n{summary_text}\n\n### Extracted Content\n{full_text[:args.max_chars]}"
    finally:
        store.close()

    payload = payload[: args.max_chars]
    if args.json:
        print(json.dumps({"item_id": item.get("item_id"), "mode": args.mode, "context": payload}, indent=2, ensure_ascii=True))
    else:
        print(payload)
    return 0


def run_collect_and_export(args: argparse.Namespace) -> int:
    collect_rc = run_collect(args)
    if collect_rc != 0:
        return collect_rc

    cluster_args = argparse.Namespace(
        db=args.db,
        date="today",
        window_days=args.window_days,
    )
    run_cluster(cluster_args)

    for view in ["highlights", "balanced", "opportunities", "trends", "followups", "topics"]:
        export_args = argparse.Namespace(
            db=args.db,
            config=args.config,
            date="today",
            limit=args.limit,
            view=view,
            include_tags=args.include_tags,
            exclude_tags=args.exclude_tags,
        )
        run_export(export_args)
    return 0


def run_morning_brief(args: argparse.Namespace) -> int:
    brief_date = resolve_date(args.date)

    collect_args = argparse.Namespace(
        config=args.config,
        db=args.db,
        watchlist=args.watchlist,
        dry_run=args.dry_run,
        refresh_discovery=args.refresh_discovery,
    )
    collect_rc = run_collect(collect_args)
    if collect_rc != 0:
        return collect_rc

    cluster_args = argparse.Namespace(
        db=args.db,
        date=brief_date,
        window_days=args.window_days,
    )
    cluster_rc = run_cluster(cluster_args)
    if cluster_rc != 0:
        return cluster_rc

    for view in ["balanced", "trends", "opportunities", "followups", "topics"]:
        export_args = argparse.Namespace(
            db=args.db,
            config=args.config,
            date=brief_date,
            limit=args.limit,
            view=view,
            include_tags="",
            exclude_tags="",
        )
        run_export(export_args)

    brief_path = write_daily_brief(
        date_str=brief_date,
        db_path=args.db,
        enable_exec_summary=not args.no_exec_summary,
        exec_summary_model=args.exec_summary_model,
    )
    print(f"Daily brief for {brief_date} written: {brief_path}")
    print(f"python -m briefbot summarize --item rank:opportunities:3 --date {brief_date}")
    print(f"python -m briefbot summarize --item rank:balanced:12 --date {brief_date}")
    print(f"python -m briefbot find --q \"recurrent language model\" --date {brief_date}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="briefbot", description="Morning Brief Collector")
    parser.add_argument("--config", default="sources.yaml", help="Path to sources YAML")
    parser.add_argument("--db", default=os.getenv("BRIEFBOT_DB_PATH", "data/briefbot.db"), help="SQLite database path")
    parser.add_argument("--watchlist", default="watchlist.yaml", help="Path to watchlist YAML")

    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_p = subparsers.add_parser("collect", help="Collect items from configured sources")
    collect_p.add_argument("--dry-run", action="store_true", help="Fetch/parse but do not write to DB")
    collect_p.add_argument("--refresh-discovery", action="store_true", help="Ignore cached site discovery")
    collect_p.set_defaults(func=run_collect)

    cluster_p = subparsers.add_parser("cluster", help="Build storyline clusters over a recent window")
    cluster_p.add_argument("--date", default="today", help="Date (YYYY-MM-DD|today|yesterday)")
    cluster_p.add_argument("--window-days", type=int, default=14, help="Window size for clustering")
    cluster_p.set_defaults(func=run_cluster)

    export_p = subparsers.add_parser("export", help="Export top items for a date")
    export_p.add_argument("--date", default="today", help="Date (YYYY-MM-DD|today|yesterday)")
    export_p.add_argument("--limit", type=int, default=50, help="Max items to export")
    export_p.add_argument(
        "--view",
        default="highlights",
        choices=["highlights", "balanced", "opportunities", "trends", "followups", "topics"],
    )
    export_p.add_argument("--include-tags", default="", help="Comma-separated include tags")
    export_p.add_argument("--exclude-tags", default="", help="Comma-separated exclude tags")
    export_p.set_defaults(func=run_export)

    run_p = subparsers.add_parser("run", help="Collect then cluster and export")
    run_p.add_argument("--dry-run", action="store_true", help="Collect dry-run mode")
    run_p.add_argument("--refresh-discovery", action="store_true", help="Ignore cached site discovery")
    run_p.add_argument("--window-days", type=int, default=14, help="Window size for clustering")
    run_p.add_argument("--limit", type=int, default=50, help="Max items to export")
    run_p.add_argument("--include-tags", default="", help="Comma-separated include tags")
    run_p.add_argument("--exclude-tags", default="", help="Comma-separated exclude tags")
    run_p.set_defaults(func=run_collect_and_export)

    topics_p = subparsers.add_parser("topics", help="Compute and export topic profiles")
    topics_p.add_argument("--date", default="today", help="Date (YYYY-MM-DD|today|yesterday)")
    topics_p.add_argument("--window-days", type=int, default=30, help="Window size for topic profiling")
    topics_p.add_argument("--limit", type=int, default=50, help="Max topics to export")
    topics_p.set_defaults(func=run_topics)

    morning_p = subparsers.add_parser("morning-brief", help="Run morning workflow and compose single daily brief")
    morning_p.add_argument("--date", default="today", help="Date (YYYY-MM-DD|today|yesterday)")
    morning_p.add_argument("--window-days", type=int, default=14, help="Window size for clustering")
    morning_p.add_argument("--limit", type=int, default=50, help="Max items per exported view")
    morning_p.add_argument("--dry-run", action="store_true", help="Collect dry-run mode")
    morning_p.add_argument("--refresh-discovery", action="store_true", help="Ignore cached site discovery")
    morning_p.add_argument("--no-exec-summary", action="store_true", help="Disable LLM executive summary sections")
    morning_p.add_argument("--exec-summary-model", default=None, help="Override model for executive summaries")
    morning_p.set_defaults(func=run_morning_brief)

    find_p = subparsers.add_parser("find", help="Find items by query")
    find_p.add_argument("--q", required=True, help="Search query")
    find_p.add_argument("--date", default=None, help="Date (YYYY-MM-DD|today|yesterday)")
    find_p.add_argument("--limit", type=int, default=20, help="Max matches")
    find_p.add_argument("--include-tags", default="", help="Comma-separated include tags")
    find_p.add_argument("--exclude-tags", default="", help="Comma-separated exclude tags")
    find_p.add_argument("--json", action="store_true", help="JSON output")
    find_p.set_defaults(func=run_find)

    cite_p = subparsers.add_parser("cite", help="Print stable citation block for an item")
    cite_p.add_argument("--item", required=True, help="Item ID")
    cite_p.add_argument("--format", default="md", choices=["md", "text", "json"])
    cite_p.set_defaults(func=run_cite)

    get_p = subparsers.add_parser("get", help="Fetch and cache article text for an item")
    get_p.add_argument("--item", required=True, help="Item ID or rank:N")
    get_p.add_argument("--date", default="today", help="Date for rank resolution")
    get_p.add_argument("--force", action="store_true", help="Refetch even if cache exists")
    get_p.add_argument("--max-bytes", type=int, default=2_000_000)
    get_p.add_argument("--max-chars", type=int, default=12_000)
    get_p.add_argument("--cache-dir", default=_default_cache_dir())
    get_p.add_argument("--json", action="store_true", help="JSON output")
    get_p.set_defaults(func=run_get)

    context_p = subparsers.add_parser("context", help="Emit LLM-ready context for an item")
    context_p.add_argument("--item", required=True, help="Item ID or rank:N")
    context_p.add_argument("--date", default="today", help="Date for rank resolution")
    context_p.add_argument("--mode", default="summary", choices=["summary", "full"])
    context_p.add_argument("--force", action="store_true", help="Refetch article cache for full mode")
    context_p.add_argument("--max-bytes", type=int, default=2_000_000)
    context_p.add_argument("--max-chars", type=int, default=12_000)
    context_p.add_argument("--provider", default=None, choices=["anthropic", "openai"])
    context_p.add_argument("--model", default=None)
    context_p.add_argument("--cache-dir", default=_default_cache_dir())
    context_p.add_argument("--summary-dir", default=_default_summary_dir())
    context_p.add_argument("--json", action="store_true", help="JSON output")
    context_p.set_defaults(func=run_context)

    summarize_p = subparsers.add_parser("summarize", help="Generate and cache structured LLM summary")
    summarize_p.add_argument("--item", required=True, help="Item ID or rank:N")
    summarize_p.add_argument("--date", default="today", help="Date for rank resolution")
    summarize_p.add_argument("--force", action="store_true", help="Regenerate summary even if cache hash matches")
    summarize_p.add_argument("--provider", default=None, choices=["anthropic", "openai"])
    summarize_p.add_argument("--model", default=None)
    summarize_p.add_argument("--cache-dir", default=_default_cache_dir())
    summarize_p.add_argument("--summary-dir", default=_default_summary_dir())
    summarize_p.add_argument("--max-chars", type=int, default=12_000)
    summarize_p.add_argument("--json", action="store_true", help="JSON output")
    summarize_p.set_defaults(func=run_summarize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
