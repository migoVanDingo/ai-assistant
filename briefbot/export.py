"""Daily digest exporters.

Reads ranked items from `briefbot.store`, applies optional tag filters, then
writes:
- JSON payload for downstream summarizers
- Markdown index for quick human browsing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def export_daily_digest(
    store,
    date_str: str,
    limit: int = 50,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    out_dir: str | Path = "data/daily_digest",
) -> tuple[Path, Path, int]:
    items = store.get_items_for_date(date_str, limit=limit * 4)
    items = _apply_tag_filters(items, include_tags=include_tags, exclude_tags=exclude_tags)
    items = sorted(items, key=lambda x: x.get("score", 0.0), reverse=True)[:limit]

    out_path = ensure_dir(out_dir)
    json_path = out_path / f"{date_str}.json"
    md_path = out_path / f"{date_str}.md"

    payload = {
        "date": date_str,
        "count": len(items),
        "items": items,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    lines = [f"# Morning Brief {date_str}", ""]
    for idx, item in enumerate(items, start=1):
        tags = ", ".join(item.get("tags", []))
        title = item.get("title", "(untitled)")
        url = item.get("url") or ""
        score = item.get("score", 0)
        lines.append(f"{idx}. [{title}]({url})  ")
        lines.append(f"   Source: `{item.get('source_name')}` | Score: `{score}` | Tags: `{tags}`")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path, len(items)
