"""Daily digest exporters for highlights, balanced, opportunities, trends, and followups views.

Reads ranked items/clusters from `briefbot.store`, applies optional filters, and
writes JSON + Markdown outputs under `data/daily_digest/`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .score import MISSION_KEYWORDS, title_matches_keywords
from .util import ensure_dir


def _apply_tag_filters(
    items: list[dict[str, Any]], include_tags: list[str] | None = None, exclude_tags: list[str] | None = None
) -> list[dict[str, Any]]:
    include = {t.lower() for t in (include_tags or [])}
    exclude = {t.lower() for t in (exclude_tags or [])}

    out: list[dict[str, Any]] = []
    for item in items:
        tags = {t.lower() for t in item.get("tags", [])}
        if include and not (tags & include):
            continue
        if exclude and (tags & exclude):
            continue
        out.append(item)
    return out


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: (x.get("score", 0.0), x.get("published_at") or ""), reverse=True)


def _sort_opportunities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda x: (
            float(x.get("score_opportunity") if x.get("score_opportunity") is not None else x.get("score", 0.0)),
            float(x.get("score", 0.0)),
            x.get("published_at") or "",
        ),
        reverse=True,
    )


def _select_highlights(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return _sort_items(items)[:limit]


def _tier3_allowed(item: dict[str, Any]) -> bool:
    return bool(item.get("watch_hits")) or title_matches_keywords(item.get("title") or "", MISSION_KEYWORDS)


def _select_balanced(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = _sort_items(items)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    source_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)

    def try_add(item: dict[str, Any], enforce_caps: bool = True) -> bool:
        iid = item.get("item_id")
        if not iid or iid in selected_ids:
            return False
        category = (item.get("source_category") or "tech_news").lower()
        source_id = item.get("source_id") or ""

        if enforce_caps and category == "aggregator":
            agg_cap = 12
            if category_counts["aggregator"] >= agg_cap:
                return False
            max_daily = int(item.get("source_max_daily") or 6)
            if source_counts[source_id] >= max_daily:
                return False

        if int(item.get("source_tier") or 2) >= 3 and not _tier3_allowed(item):
            return False

        selected.append(item)
        selected_ids.add(iid)
        source_counts[source_id] += 1
        category_counts[category] += 1
        return True

    for item in ranked[:15]:
        if len(selected) >= limit:
            break
        try_add(item, enforce_caps=False)

    quotas = {
        "papers": 10,
        "security": 10,
        "ai_combined": 8,
        "dev_mlops_combined": 7,
        "tech_news": 8,
    }

    for item in ranked:
        if len(selected) >= limit:
            break
        cat = (item.get("source_category") or "tech_news").lower()
        ai_combined = category_counts["ai_research"] + category_counts["ai_industry"]
        devops_combined = category_counts["devtools"] + category_counts["mlops_infra"]

        if cat == "papers" and category_counts[cat] < quotas["papers"]:
            try_add(item)
        elif cat == "security" and category_counts[cat] < quotas["security"]:
            try_add(item)
        elif cat in {"ai_research", "ai_industry"} and ai_combined < quotas["ai_combined"]:
            try_add(item)
        elif cat in {"devtools", "mlops_infra"} and devops_combined < quotas["dev_mlops_combined"]:
            try_add(item)
        elif cat == "tech_news" and category_counts[cat] < quotas["tech_news"]:
            try_add(item)
        elif cat == "aggregator":
            try_add(item)

    for item in ranked:
        if len(selected) >= limit:
            break
        try_add(item)

    # Hard-cap aggregators after selection, including items from the initial global seed.
    selected = _sort_items(selected)
    agg_items = [i for i in selected if (i.get("source_category") or "").lower() == "aggregator"]
    if len(agg_items) > 12:
        overflow = len(agg_items) - 12
        drop_ids = {i.get("item_id") for i in agg_items[-overflow:]}
        selected = [i for i in selected if i.get("item_id") not in drop_ids]

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in selected:
        by_source[item.get("source_id") or ""].append(item)
    drop_source_ids: set[str] = set()
    for source_id, vals in by_source.items():
        vals = [i for i in vals if (i.get("source_category") or "").lower() == "aggregator"]
        if not vals:
            continue
        max_daily = int(vals[0].get("source_max_daily") or 6)
        if len(vals) > max_daily:
            overflow = len(vals) - max_daily
            for item in vals[-overflow:]:
                drop_source_ids.add(item.get("item_id"))
    if drop_source_ids:
        selected = [i for i in selected if i.get("item_id") not in drop_source_ids]

    tier12 = sum(1 for i in selected if int(i.get("source_tier") or 2) <= 2)
    required_tier12 = int(limit * 0.6)
    if selected and tier12 < required_tier12:
        tier3_indices = [
            idx for idx, item in enumerate(selected) if int(item.get("source_tier") or 2) >= 3 and not _tier3_allowed(item)
        ]
        for idx in reversed(tier3_indices):
            if tier12 >= required_tier12:
                break
            selected.pop(idx)
        selected = _sort_items(selected)

    return _sort_items(selected)[:limit]


def _select_opportunities(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ranked = _sort_opportunities(items)
    selected: list[dict[str, Any]] = []
    agg_count = 0
    for item in ranked:
        if len(selected) >= limit:
            break
        if (item.get("source_category") or "").lower() == "aggregator":
            if agg_count >= 12:
                continue
            agg_count += 1
        selected.append(item)
    return selected


def _select_trends(store, date_str: str, limit: int) -> list[dict[str, Any]]:
    clusters = store.fetch_clusters_for_date(date_str=date_str, limit=max(limit * 2, 50))
    clusters = sorted(clusters, key=lambda c: (c.get("trend_score", 0.0), c.get("velocity_1d", 0)), reverse=True)

    out: list[dict[str, Any]] = []
    for cluster in clusters[:limit]:
        members = store.fetch_cluster_members(cluster["cluster_id"], limit=3)
        out.append(
            {
                "cluster_id": cluster["cluster_id"],
                "label": cluster.get("label") or "general update",
                "trend_score": cluster.get("trend_score", 0.0),
                "velocity_1d": cluster.get("velocity_1d", 0),
                "velocity_3d": cluster.get("velocity_3d", 0),
                "velocity_7d": cluster.get("velocity_7d", 0),
                "sources_count": cluster.get("sources_count", 0),
                "diversity_score": cluster.get("diversity_score", 0.0),
                "representative_title": cluster.get("representative_title"),
                "representative_url": cluster.get("representative_url"),
                "top_items": [
                    {
                        "title": m.get("title"),
                        "url": m.get("url"),
                        "source_name": m.get("source_name"),
                        "score": m.get("score"),
                    }
                    for m in members
                ],
            }
        )
    return out


def _select_followups(store, date_str: str, limit: int) -> list[dict[str, Any]]:
    candidates = store.get_followup_candidates(date_str)
    if not candidates:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for row in candidates:
        cid = row["cluster_id"]
        if cid not in grouped:
            grouped[cid] = {
                "cluster_id": cid,
                "label": row.get("label") or "general update",
                "trend_score": row.get("trend_score", 0.0),
                "first_seen_at": row.get("first_seen_at"),
                "last_seen_at": row.get("last_seen_at"),
                "new_items": [],
                "why": {
                    "velocity_1d": row.get("velocity_1d", 0),
                    "velocity_7d": row.get("velocity_7d", 0),
                    "sources_count": row.get("sources_count", 0),
                },
            }
        grouped[cid]["new_items"].append(
            {
                "item_id": row.get("item_id"),
                "title": row.get("title"),
                "url": row.get("url"),
                "source_name": row.get("source_name"),
                "score": row.get("score"),
                "published_at": row.get("published_at"),
            }
        )

    items = sorted(grouped.values(), key=lambda g: g.get("trend_score", 0.0), reverse=True)[:limit]
    for block in items:
        cid = block["cluster_id"]
        older = store.fetch_cluster_members(cid, limit=8)
        new_ids = {n.get("item_id") for n in block["new_items"]}
        previously = [m for m in older if m.get("item_id") not in new_ids]
        block["previous_items"] = [
            {
                "item_id": m.get("item_id"),
                "title": m.get("title"),
                "url": m.get("url"),
                "source_name": m.get("source_name"),
                "score": m.get("score"),
            }
            for m in previously[:2]
        ]
        block["new_items"] = _sort_items(block["new_items"])[:5]
    return items


def _write_highlights_markdown(path: Path, date_str: str, view: str, items: list[dict[str, Any]]) -> None:
    lines = [f"# Morning Brief {date_str} ({view})", ""]
    for idx, item in enumerate(items, start=1):
        tags = ", ".join(item.get("tags", []))
        title = item.get("title", "(untitled)")
        url = item.get("url") or ""
        score = item.get("score", 0)
        lines.append(f"{idx}. [{title}]({url})  ")
        lines.append(f"   Source: `{item.get('source_name')}` | Score: `{score}` | Tags: `{tags}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_trends_markdown(path: Path, date_str: str, data: list[dict[str, Any]]) -> None:
    lines = [f"# Morning Brief {date_str} (trends)", ""]
    for idx, cluster in enumerate(data, start=1):
        rep_title = cluster.get("representative_title") or cluster.get("label")
        rep_url = cluster.get("representative_url") or ""
        lines.append(
            f"{idx}. **{cluster.get('label')}** | trend=`{cluster.get('trend_score')}` | "
            f"v7d=`{cluster.get('velocity_7d')}` | sources=`{cluster.get('sources_count')}`"
        )
        lines.append(f"   Representative: [{rep_title}]({rep_url})")
        for item in cluster.get("top_items", [])[:3]:
            lines.append(f"   - [{item.get('title')}]({item.get('url')}) ({item.get('source_name')})")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_followups_markdown(path: Path, date_str: str, data: list[dict[str, Any]]) -> None:
    lines = [f"# Morning Brief {date_str} (followups)", ""]
    for idx, cluster in enumerate(data, start=1):
        why = cluster.get("why") or {}
        lines.append(
            f"{idx}. **{cluster.get('label')}** | trend=`{cluster.get('trend_score')}` | "
            f"new24h=`{why.get('velocity_1d')}` | sources=`{why.get('sources_count')}`"
        )
        lines.append("   New today:")
        for item in cluster.get("new_items", []):
            lines.append(f"   - [{item.get('title')}]({item.get('url')}) ({item.get('source_name')})")
        if cluster.get("previous_items"):
            lines.append("   Previously:")
            for item in cluster.get("previous_items", []):
                lines.append(f"   - [{item.get('title')}]({item.get('url')}) ({item.get('source_name')})")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_opportunities_markdown(path: Path, date_str: str, items: list[dict[str, Any]]) -> None:
    lines = [f"# Morning Brief {date_str} (opportunities)", ""]
    for idx, item in enumerate(items, start=1):
        title = item.get("title", "(untitled)")
        url = item.get("url") or ""
        source = item.get("source_name")
        score_opp = item.get("score_opportunity")
        score = item.get("score")
        tags = ", ".join(item.get("tags", []))
        opp_tags = ", ".join(item.get("opportunity_tags", []))
        reason = item.get("opportunity_reason")

        lines.append(f"{idx}. [{title}]({url})")
        lines.append(f"   Source: `{source}` | score_opportunity: `{score_opp}` | score: `{score}`")
        lines.append(f"   Tags: `{tags}` | Opportunity tags: `{opp_tags}`")
        if reason:
            lines.append(f"   Reason: {reason}")
        lines.append(f"   Ref: rank:opportunities:{idx} | item: {item.get('item_id')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def export_daily_digest(
    store,
    date_str: str,
    limit: int = 50,
    view: str = "highlights",
    config_path: str = "sources.yaml",
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    out_dir: str | Path = "data/daily_digest",
) -> tuple[Path, Path, int]:
    view = (view or "highlights").lower()
    out_path = ensure_dir(out_dir)
    json_path = out_path / f"{date_str}.{view}.json"
    md_path = out_path / f"{date_str}.{view}.md"

    if view in {"highlights", "balanced", "opportunities"}:
        items = store.get_items_for_date(date_str, limit=limit * 6)
        items = _apply_tag_filters(items, include_tags=include_tags, exclude_tags=exclude_tags)
        if view == "highlights":
            selected = _select_highlights(items, limit)
            markdown_writer = _write_highlights_markdown
        elif view == "opportunities":
            selected = _select_opportunities(items, limit)
            markdown_writer = None
        else:
            selected = _select_balanced(items, limit)
            markdown_writer = _write_highlights_markdown

        payload = {
            "date": date_str,
            "view": view,
            "count": len(selected),
            "items": selected,
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        if view == "opportunities":
            _write_opportunities_markdown(md_path, date_str, selected)
        else:
            markdown_writer(md_path, date_str, view, selected)
        return json_path, md_path, len(selected)

    if view == "trends":
        clusters = _select_trends(store, date_str, limit)
        payload = {
            "date": date_str,
            "view": view,
            "count": len(clusters),
            "clusters": clusters,
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        _write_trends_markdown(md_path, date_str, clusters)
        return json_path, md_path, len(clusters)

    if view == "followups":
        followups = _select_followups(store, date_str, limit)
        payload = {
            "date": date_str,
            "view": view,
            "count": len(followups),
            "clusters": followups,
        }
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        _write_followups_markdown(md_path, date_str, followups)
        return json_path, md_path, len(followups)

    raise ValueError(f"Unsupported export view: {view}")
