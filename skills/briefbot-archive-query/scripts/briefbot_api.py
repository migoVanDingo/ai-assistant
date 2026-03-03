#!/usr/bin/env python3
"""Helper for querying a local Briefbot backend over HTTP."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _base_url() -> str:
    return (os.getenv("BRIEFBOT_API_BASE", "http://127.0.0.1:8000").rstrip("/") + "/")


def _request_json(method: str, path: str, payload: dict | None = None) -> dict | list:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(urljoin(_base_url(), path.lstrip("/")), data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed: {exc}") from exc


def _today() -> date:
    return date.today()


def _window_to_dates(window: str) -> tuple[str, str]:
    today = _today()
    if window == "today":
        return today.isoformat(), today.isoformat()
    if window == "yesterday":
        d = today - timedelta(days=1)
        return d.isoformat(), d.isoformat()
    if window == "last-week":
        return (today - timedelta(days=7)).isoformat(), today.isoformat()
    if window == "this-month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if window == "last-month":
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        return first_prev_month.isoformat(), last_prev_month.isoformat()
    raise SystemExit(f"Unsupported window: {window}")


def cmd_ask(args: argparse.Namespace) -> None:
    payload: dict[str, str] = {"query": args.query}
    if args.provider:
        payload["provider"] = args.provider
    if args.model:
        payload["model"] = args.model
    result = _request_json("POST", "/api/query", payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_summarize(args: argparse.Namespace) -> None:
    query = f"summarize {args.title}"
    payload: dict[str, str] = {"query": query}
    if args.provider:
        payload["provider"] = args.provider
    if args.model:
        payload["model"] = args.model
    result = _request_json("POST", "/api/query", payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_stories(args: argparse.Namespace) -> None:
    from_date = args.from_date
    to_date = args.to_date
    if args.window:
        from_date, to_date = _window_to_dates(args.window)

    payload = {
        "source_name": args.source,
        "from_date": from_date,
        "to_date": to_date,
        "limit": args.limit,
        "cluster_id": args.cluster_id,
        "tags": args.tag or [],
        "watch_hits": args.watch_hit or [],
        "order": args.order,
    }
    result = _request_json("POST", "/api/stories", payload)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_meta(args: argparse.Namespace) -> None:
    endpoint = {
        "sources": "/api/stories/sources",
        "clusters": "/api/stories/clusters",
        "tags": "/api/stories/tags",
        "watch-hits": "/api/stories/watch-hits",
        "queries": "/api/queries",
    }[args.kind]
    result = _request_json("GET", endpoint)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="briefbot_api", description="Query a local Briefbot backend over HTTP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_p = subparsers.add_parser("ask", help="Ask the Briefbot archive a natural-language question")
    ask_p.add_argument("--query", required=True)
    ask_p.add_argument("--provider")
    ask_p.add_argument("--model")
    ask_p.set_defaults(func=cmd_ask)

    summarize_p = subparsers.add_parser("summarize", help="Summarize an article by title through the Briefbot backend")
    summarize_p.add_argument("--title", required=True)
    summarize_p.add_argument("--provider")
    summarize_p.add_argument("--model")
    summarize_p.set_defaults(func=cmd_summarize)

    stories_p = subparsers.add_parser("stories", help="Run a deterministic stories query")
    stories_p.add_argument("--window", choices=["today", "yesterday", "last-week", "last-month", "this-month"])
    stories_p.add_argument("--from-date")
    stories_p.add_argument("--to-date")
    stories_p.add_argument("--source")
    stories_p.add_argument("--cluster-id")
    stories_p.add_argument("--tag", action="append")
    stories_p.add_argument("--watch-hit", action="append")
    stories_p.add_argument("--limit", type=int, default=20)
    stories_p.add_argument("--order", choices=["asc", "desc"], default="desc")
    stories_p.set_defaults(func=cmd_stories)

    meta_p = subparsers.add_parser("meta", help="Fetch Briefbot metadata lists")
    meta_p.add_argument("kind", choices=["sources", "clusters", "tags", "watch-hits", "queries"])
    meta_p.set_defaults(func=cmd_meta)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
