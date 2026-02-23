"""Compose a single Obsidian-friendly daily brief from exported JSON views."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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


def _render_trends_section(lines: list[str], payload: dict[str, Any] | None) -> None:
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


def write_daily_brief(
    date_str: str,
    digest_dir: str | Path = "data/daily_digest",
    out_dir: str | Path | None = None,
) -> Path:
    digest_path = Path(digest_dir)
    if out_dir is None:
        out_dir = os.getenv("BRIEFBOT_BRIEF_DIR", "data/briefs")
    brief_dir = ensure_dir(out_dir)

    balanced = _load_json(digest_path / f"{date_str}.balanced.json")
    trends = _load_json(digest_path / f"{date_str}.trends.json")
    opportunities = _load_json(digest_path / f"{date_str}.opportunities.json")
    followups = _load_json(digest_path / f"{date_str}.followups.json")

    lines: list[str] = [f"# Morning Brief {date_str}", ""]
    _render_items_section(lines, "Balanced", "balanced", balanced)
    _render_trends_section(lines, trends)
    _render_items_section(lines, "Opportunities", "opportunities", opportunities)
    _render_followups_section(lines, followups)

    out_path = Path(brief_dir) / f"{date_str}.daily.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
