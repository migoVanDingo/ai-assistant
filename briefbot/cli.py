"""Command-line orchestration for collect/export workflows.

Subcommands:
- `collect`: load config, fetch all sources, score, and store items
- `export`: write daily JSON/Markdown digest from stored items
- `run`: collect then export in one command

This module coordinates `config`, `discover`, `fetch`, `score`, `store`, and
`export`, and keeps source errors isolated so one failure does not stop the run.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from typing import Any

import requests

from .config import load_config
from .discover import discover_site_feeds
from .export import export_daily_digest
from .fetch import FetchError, fetch_arxiv_source, fetch_hn_source, fetch_rss_feed, source_homepage
from .score import compute_score
from .store import Store


def _resolve_date(value: str) -> str:
    if value == "today":
        return date.today().isoformat()
    if value == "yesterday":
        from datetime import timedelta

        return (date.today() - timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid --date '{value}'. Use YYYY-MM-DD, today, or yesterday.") from exc


def _parse_csv_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _rss_fallback_collect(
    source: dict[str, Any],
    store: Store,
    session: requests.Session,
) -> list[dict[str, Any]]:
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


def run_collect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
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
                feed_urls = store.get_discovered_feeds(source["url"], max_age_days=7)
                if feed_urls is None:
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

            elif source["type"] == "hn":
                source_items.extend(fetch_hn_source(source, session=session))

            elif source["type"] == "arxiv":
                source_items.extend(fetch_arxiv_source(source, session=session))

            else:
                raise FetchError(f"Unsupported source type: {source['type']}")

            source_weight = float(source.get("weight", 1.0))
            for item in source_items:
                item["score"] = compute_score(item, source_weight=source_weight)
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


def run_export(args: argparse.Namespace) -> int:
    export_date = _resolve_date(args.date)
    include_tags = _parse_csv_arg(args.include_tags)
    exclude_tags = _parse_csv_arg(args.exclude_tags)

    store = Store(args.db)
    json_path, md_path, count = export_daily_digest(
        store=store,
        date_str=export_date,
        limit=args.limit,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )
    store.close()

    print(f"Exported {count} items")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


def run_collect_and_export(args: argparse.Namespace) -> int:
    collect_rc = run_collect(args)
    if collect_rc != 0:
        return collect_rc

    export_args = argparse.Namespace(
        db=args.db,
        date="today",
        limit=args.limit,
        include_tags=args.include_tags,
        exclude_tags=args.exclude_tags,
    )
    return run_export(export_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="briefbot", description="Morning Brief Collector")
    parser.add_argument("--config", default="sources.yaml", help="Path to sources YAML")
    parser.add_argument("--db", default="data/briefbot.db", help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_p = subparsers.add_parser("collect", help="Collect items from configured sources")
    collect_p.add_argument("--dry-run", action="store_true", help="Fetch/parse but do not write to DB")
    collect_p.set_defaults(func=run_collect)

    export_p = subparsers.add_parser("export", help="Export top items for a date")
    export_p.add_argument("--date", default="today", help="Date (YYYY-MM-DD|today|yesterday)")
    export_p.add_argument("--limit", type=int, default=50, help="Max items to export")
    export_p.add_argument("--include-tags", default="", help="Comma-separated include tags")
    export_p.add_argument("--exclude-tags", default="", help="Comma-separated exclude tags")
    export_p.set_defaults(func=run_export)

    run_p = subparsers.add_parser("run", help="Collect then export for today")
    run_p.add_argument("--dry-run", action="store_true", help="Collect dry-run mode")
    run_p.add_argument("--limit", type=int, default=50, help="Max items to export")
    run_p.add_argument("--include-tags", default="", help="Comma-separated include tags")
    run_p.add_argument("--exclude-tags", default="", help="Comma-separated exclude tags")
    run_p.set_defaults(func=run_collect_and_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
