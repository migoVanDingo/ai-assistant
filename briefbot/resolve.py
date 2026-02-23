"""Helpers for date parsing, rank resolution, search ranking, and citations.

These helpers support retrieval-oriented CLI commands (`find`, `cite`, `context`,
`get`, `summarize`) without depending on network access.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dateutil import parser as dtparser


def resolve_date(value: str) -> str:
    if value == "today":
        return date.today().isoformat()
    if value == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD, today, or yesterday.") from exc


def _load_ranked_items_from_export(date_str: str, digest_dir: str | Path = "data/daily_digest") -> list[dict[str, Any]]:
    base = Path(digest_dir)
    candidates = [
        base / f"{date_str}.balanced.json",
        base / f"{date_str}.json",
        base / f"{date_str}.highlights.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = payload.get("items")
        if isinstance(items, list) and items:
            return items
    return []


def _load_ranked_items_for_view(
    date_str: str,
    view: str,
    digest_dir: str | Path = "data/daily_digest",
) -> list[dict[str, Any]]:
    base = Path(digest_dir)
    path = base / f"{date_str}.{view}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    items = payload.get("items")
    if isinstance(items, list):
        return items
    return []


def resolve_item_reference(
    store,
    item_ref: str,
    date_str: str,
    digest_dir: str | Path = "data/daily_digest",
) -> str:
    ref = (item_ref or "").strip()
    if not ref:
        raise ValueError("--item is required")

    if not ref.lower().startswith("rank:"):
        return ref

    parts = ref.split(":")
    rank_view: str | None = None
    rank_raw = ""
    if len(parts) == 2:
        rank_raw = parts[1].strip()
    elif len(parts) == 3:
        rank_view = parts[1].strip().lower()
        rank_raw = parts[2].strip()
    else:
        raise ValueError(
            f"Invalid rank reference: {item_ref}. Use rank:<n> or rank:<view>:<n>"
        )

    if not rank_raw.isdigit():
        raise ValueError(
            f"Invalid rank reference: {item_ref}. Rank must be numeric."
        )
    rank = int(rank_raw)
    if rank <= 0:
        raise ValueError(f"Invalid rank value: {rank}")

    items: list[dict[str, Any]]
    if rank_view:
        items = _load_ranked_items_for_view(date_str, rank_view, digest_dir=digest_dir)
    else:
        items = _load_ranked_items_from_export(date_str, digest_dir=digest_dir)
    if len(items) >= rank:
        iid = items[rank - 1].get("item_id")
        if iid:
            return iid

    fallback_view = rank_view or "highlights"
    if hasattr(store, "get_items_for_date_by_view"):
        fallback = store.get_items_for_date_by_view(
            date_str,
            limit=max(250, rank + 20),
            view=fallback_view,
        )
    else:
        fallback = store.get_items_for_date(date_str, limit=max(250, rank + 20))
    if len(fallback) < rank:
        if rank_view:
            raise ValueError(
                f"Could not resolve rank:{rank_view}:{rank} for date {date_str}"
            )
        raise ValueError(f"Could not resolve rank:{rank} for date {date_str}")
    iid = fallback[rank - 1].get("item_id")
    if not iid:
        raise ValueError(f"Resolved item for rank:{rank} has no item_id")
    return iid


def _to_dt(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        dt = dtparser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def rank_items_for_query(query: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9_\-\.]+", query or "") if t]
    now = datetime.now(timezone.utc)

    ranked: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").lower()
        summary = (item.get("summary") or "").lower()
        source_name = (item.get("source_name") or "").lower()
        tags_blob = " ".join(str(t).lower() for t in (item.get("tags") or []))

        match_score = 0.0
        for tok in tokens:
            if tok in title:
                match_score += 3.0
            if tok in summary:
                match_score += 1.5
            if tok in tags_blob:
                match_score += 1.2
            if tok in source_name:
                match_score += 1.0

        age_days = (now - _to_dt(item.get("published_at") or item.get("fetched_at"))).total_seconds() / 86400.0
        recency_boost = max(0.0, 1.0 - min(age_days, 14.0) / 14.0)
        item_score = float(item.get("score") or 0.0)

        total = match_score + (item_score * 0.12) + recency_boost
        enriched = dict(item)
        enriched["query_score"] = round(total, 4)
        ranked.append(enriched)

    ranked.sort(key=lambda x: (x.get("query_score", 0.0), x.get("score", 0.0)), reverse=True)
    return ranked


def format_citation(item: dict[str, Any], fmt: str = "md") -> str | dict[str, Any]:
    data = {
        "title": item.get("title"),
        "source_name": item.get("source_name"),
        "source_id": item.get("source_id"),
        "published_at": item.get("published_at"),
        "url": item.get("canonical_url") or item.get("url"),
        "tags": item.get("tags") or [],
        "item_id": item.get("item_id"),
    }

    if fmt == "json":
        return data
    if fmt == "text":
        tags = ", ".join(data["tags"])
        return (
            f"{data['title']}\n"
            f"Source: {data['source_name']} ({data['source_id']})\n"
            f"Published: {data['published_at']}\n"
            f"URL: {data['url']}\n"
            f"Tags: {tags}\n"
            f"Item ID: {data['item_id']}"
        )

    tags = ", ".join(data["tags"])
    return (
        f"### Citation\n"
        f"- **Title:** {data['title']}\n"
        f"- **Source:** {data['source_name']} (`{data['source_id']}`)\n"
        f"- **Published:** {data['published_at']}\n"
        f"- **URL:** {data['url']}\n"
        f"- **Tags:** {tags}\n"
        f"- **Item ID:** `{data['item_id']}`"
    )
