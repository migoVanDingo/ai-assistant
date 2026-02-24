"""Compose a single Obsidian-friendly daily brief from exported JSON views."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dateutil import parser as dtparser

from .store import Store
from .util import ensure_dir


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _render_items_section(lines: list[str], title: str, view: str, payload: dict[str, Any] | None) -> None:
    lines.append(f"## {title}")
    if not payload:
        lines.append(f"_No export found for `{view}` view._")
        lines.append("")
        return

    items = payload.get("items") or []
    if not items:
        lines.append("_No items._")
        lines.append("")
        return

    for idx, item in enumerate(items, start=1):
        item_title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        source = item.get("source_name") or ""
        score = item.get("score")
        score_opp = item.get("score_opportunity")
        tags = ", ".join(item.get("tags") or [])
        lines.append(f"{idx}. [{item_title}]({url})")
        if view == "opportunities":
            lines.append(f"   Source: `{source}` | score_opportunity: `{score_opp}` | score: `{score}`")
        else:
            lines.append(f"   Source: `{source}` | score: `{score}`")
        lines.append(f"   Tags: `{tags}`")
        lines.append(f"   Ref: rank:{view}:{idx} | item: {item.get('item_id')}")
    lines.append("")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_paper_item(item: dict[str, Any]) -> bool:
    if (item.get("source_category") or "").lower() == "papers":
        return True
    domain = urlparse(item.get("url") or "").netloc.lower()
    return "arxiv" in domain


def _is_recent_paper(item: dict[str, Any], brief_date: datetime) -> bool:
    pub_dt = _parse_dt(item.get("published_at") or item.get("fetched_at"))
    if not pub_dt:
        return False
    return pub_dt >= (brief_date - timedelta(days=7))


def _render_balanced_section(
    lines: list[str],
    payload: dict[str, Any] | None,
    date_str: str,
    db_path: str | Path | None,
    ctx: dict[str, Any] | None = None,
) -> None:
    lines.append("## Balanced")
    if not payload:
        lines.append("_No export found for `balanced` view._")
        lines.append("")
        return

    items = payload.get("items") or []
    if not items:
        lines.append("_No items._")
        lines.append("")
        return

    item_rank = {it.get("item_id"): idx for idx, it in enumerate(items, start=1)}

    brief_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    high_signal_ids: set[str] = set()
    store: Store | None = None
    try:
        if db_path:
            store = Store(db_path)
    except Exception:
        store = None

    if store:
        try:
            for item in items:
                if not _is_paper_item(item) or not _is_recent_paper(item, brief_date):
                    continue
                iid = item.get("item_id")
                if not iid:
                    continue
                cid = store.get_cluster_for_item(iid)
                if not cid:
                    continue
                cluster = store.get_cluster(cid)
                if cluster and int(cluster.get("sources_count") or 0) >= 2:
                    high_signal_ids.add(iid)
        finally:
            store.close()

    top_links = [it for it in items if it.get("item_id") not in high_signal_ids and not _is_paper_item(it)]
    high_signal = [it for it in items if it.get("item_id") in high_signal_ids]

    if ctx is not None:
        read_item = None
        if top_links:
            first = top_links[0]
            read_item = {"item": first, "raw_idx": item_rank.get(first.get("item_id"), 1)}
        balanced_order_items: list[dict[str, Any]] = []
        for it in top_links:
            balanced_order_items.append({"item": it, "raw_idx": item_rank.get(it.get("item_id"), 1)})
        for it in high_signal:
            balanced_order_items.append({"item": it, "raw_idx": item_rank.get(it.get("item_id"), 1)})
        ctx["read_item"] = read_item
        ctx["balanced_order_items"] = balanced_order_items

    lines.append("")
    lines.append("### Top Links")
    if not top_links:
        lines.append("_No top links._")
    else:
        for display_idx, item in enumerate(top_links, start=1):
            raw_idx = item_rank.get(item.get("item_id"), display_idx)
            title = item.get("title") or "(untitled)"
            url = item.get("url") or ""
            source = item.get("source_name") or ""
            score = item.get("score")
            tags = ", ".join(item.get("tags") or [])
            lines.append(f"{display_idx}. [{title}]({url})")
            lines.append(f"   Source: `{source}` | score: `{score}`")
            lines.append(f"   Tags: `{tags}`")
            lines.append(f"   Ref: rank:balanced:{raw_idx} | item: {item.get('item_id')}")

    if high_signal:
        lines.append("")
        lines.append("### High-Signal Papers")
        for display_idx, item in enumerate(high_signal, start=1):
            raw_idx = item_rank.get(item.get("item_id"), display_idx)
            title = item.get("title") or "(untitled)"
            url = item.get("url") or ""
            source = item.get("source_name") or ""
            score = item.get("score")
            tags = ", ".join(item.get("tags") or [])
            lines.append(f"{display_idx}. [{title}]({url})")
            lines.append(f"   Source: `{source}` | score: `{score}`")
            lines.append(f"   Tags: `{tags}`")
            lines.append(f"   Ref: rank:balanced:{raw_idx} | item: {item.get('item_id')}")
    lines.append("")


def _render_trends_section(lines: list[str], payload: dict[str, Any] | None, ctx: dict[str, Any] | None = None) -> None:
    lines.append("## Trends")
    if not payload:
        lines.append("_No export found for `trends` view._")
        lines.append("")
        return

    clusters = payload.get("clusters") or []
    if not clusters:
        lines.append("_No trend clusters._")
        lines.append("")
        return

    if ctx is not None:
        ctx["track_cluster"] = clusters[0]

    for idx, c in enumerate(clusters, start=1):
        label = c.get("label") or "general update"
        rep_title = c.get("representative_title") or label
        rep_url = c.get("representative_url") or ""
        trend_score = c.get("trend_score")
        velocity_7d = c.get("velocity_7d")
        sources_count = c.get("sources_count")
        lines.append(f"{idx}. [{rep_title}]({rep_url})")
        lines.append(
            f"   Cluster: `{label}` | trend: `{trend_score}` | v7d: `{velocity_7d}` | sources: `{sources_count}`"
        )
        lines.append(f"   Ref: rank:trends:{idx} | item: {c.get('cluster_id')}")
    lines.append("")


def _is_github_url(url: str | None) -> bool:
    domain = urlparse(url or "").netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain == "github.com"


def _render_todays_moves_section(lines: list[str], ctx: dict[str, Any], opportunities_payload: dict[str, Any] | None) -> None:
    lines.append("## Today’s Moves")

    read_item = ctx.get("read_item")
    if read_item and isinstance(read_item, dict):
        item = read_item.get("item") or {}
        raw_idx = int(read_item.get("raw_idx") or 1)
        title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        lines.append(f"1. Read: [{title}]({url})")
        lines.append(f"   Ref: rank:balanced:{raw_idx} | item: {item.get('item_id')}")

    try_item: dict[str, Any] | None = None
    try_ref: str | None = None
    for entry in ctx.get("balanced_order_items") or []:
        item = entry.get("item") or {}
        if _is_github_url(item.get("url")):
            raw_idx = int(entry.get("raw_idx") or 1)
            try_item = item
            try_ref = f"rank:balanced:{raw_idx}"
            break

    if try_item is None:
        opp_items = (opportunities_payload or {}).get("items") or []
        for idx, item in enumerate(opp_items, start=1):
            if _is_github_url(item.get("url")):
                try_item = item
                try_ref = f"rank:opportunities:{idx}"
                break

    if try_item is not None and try_ref:
        title = try_item.get("title") or "(untitled)"
        url = try_item.get("url") or ""
        lines.append(f"2. Try: [{title}]({url})")
        lines.append(f"   Ref: {try_ref} | item: {try_item.get('item_id')}")

    cluster = ctx.get("track_cluster")
    if cluster and isinstance(cluster, dict):
        rep_title = cluster.get("representative_title") or cluster.get("label") or "(untitled)"
        rep_url = cluster.get("representative_url") or ""
        lines.append(f"3. Track: [{rep_title}]({rep_url})")
        lines.append(f"   Ref: rank:trends:1 | item: {cluster.get('cluster_id')}")

    lines.append("")


def _render_followups_section(lines: list[str], payload: dict[str, Any] | None) -> None:
    lines.append("## Followups")
    if not payload:
        lines.append("_No export found for `followups` view._")
        lines.append("")
        return

    clusters = payload.get("clusters") or []
    if not clusters:
        lines.append("_No follow-up clusters._")
        lines.append("")
        return

    for idx, c in enumerate(clusters, start=1):
        label = c.get("label") or "general update"
        lines.append(f"{idx}. **{label}**")
        new_items = c.get("new_items") or []
        if new_items:
            first = new_items[0]
            lines.append(f"   Lead: [{first.get('title')}]({first.get('url')})")
            lines.append(f"   Ref: rank:followups:{idx} | item: {first.get('item_id')}")
        else:
            lines.append(f"   Ref: rank:followups:{idx} | item: {c.get('cluster_id')}")
    lines.append("")


def _render_topics_section(lines: list[str], payload: dict[str, Any] | None) -> None:
    lines.append("## Topics")
    if not payload:
        lines.append("_No export found for `topics` view._")
        lines.append("")
        return

    topics = payload.get("topics") or []
    if not topics:
        lines.append("_No topics._")
        lines.append("")
        return

    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    for idx, topic in enumerate(topics, start=1):
        name = topic.get("name") or "(unnamed)"
        kind = topic.get("kind") or "token"
        momentum = topic.get("momentum")
        c1 = _to_int(topic.get("count_1d"))
        c3 = _to_int(topic.get("count_3d"))
        c7 = _to_int(topic.get("count_7d"))
        c30 = _to_int(topic.get("count_30d"))
        last_seen = topic.get("last_seen_at")
        topic_id = topic.get("topic_id") or f"topic:{name}"
        badges: list[str] = []
        if c7 > 0:
            baseline = (c7 / 7.0) * 2.5
            if c1 >= 2 and c1 >= baseline:
                badges.append("🔥")
        if c30 <= 2 and c1 >= 1:
            badges.append("🆕")
        badge_text = f" {' '.join(badges)}" if badges else ""
        lines.append(f"{idx}. **{name}**{badge_text}")
        lines.append(
            f"   Kind: `{kind}` | momentum: `{momentum}` | 1d/3d/7d/30d: `{c1}/{c3}/{c7}/{c30}` | last_seen: `{last_seen}`"
        )
        lines.append(f"   Ref: rank:topics:{idx} | item: {topic_id}")
    lines.append("")


def write_daily_brief(
    date_str: str,
    digest_dir: str | Path = "data/daily_digest",
    out_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> Path:
    digest_path = Path(digest_dir)
    if out_dir is None:
        out_dir = os.getenv("BRIEFBOT_BRIEF_DIR", "data/briefs")
    if db_path is None:
        db_path = os.getenv("BRIEFBOT_DB_PATH", "data/briefbot.db")
    brief_dir = ensure_dir(out_dir)

    balanced = _load_json(digest_path / f"{date_str}.balanced.json")
    trends = _load_json(digest_path / f"{date_str}.trends.json")
    opportunities = _load_json(digest_path / f"{date_str}.opportunities.json")
    followups = _load_json(digest_path / f"{date_str}.followups.json")
    topics = _load_json(digest_path / f"{date_str}.topics.json")
    ctx: dict[str, Any] = {}

    lines: list[str] = [f"# Morning Brief {date_str}", ""]
    _render_balanced_section(lines, balanced, date_str=date_str, db_path=db_path, ctx=ctx)
    _render_trends_section(lines, trends, ctx=ctx)
    _render_items_section(lines, "Opportunities", "opportunities", opportunities)
    _render_followups_section(lines, followups)
    _render_topics_section(lines, topics)
    _render_todays_moves_section(lines, ctx, opportunities_payload=opportunities)

    out_path = Path(brief_dir) / f"{date_str}.daily.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
