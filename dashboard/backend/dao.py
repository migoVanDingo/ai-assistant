"""Data access layer for the Morning Brief dashboard."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class DashboardConfig:
    db_path: str | Path
    briefs_dir: str | Path


class BriefbotDAO:
    def __init__(self, config: DashboardConfig) -> None:
        self.config = config
        self.conn = sqlite3.connect(str(config.db_path))
        self.conn.row_factory = sqlite3.Row
        self.briefs_dir = Path(config.briefs_dir)

    def close(self) -> None:
        self.conn.close()

    def _rows(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def _row(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = self.conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def list_briefs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self.briefs_dir.glob("*.daily.md"), reverse=True):
            date_str = path.name.replace(".daily.md", "")
            try:
                stat = path.stat()
                out.append(
                    {
                        "date": date_str,
                        "filename": path.name,
                        "path": str(path),
                        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "size_bytes": stat.st_size,
                    }
                )
            except FileNotFoundError:
                continue
        return out

    def get_brief_markdown(self, date_str: str) -> dict[str, Any] | None:
        path = self.briefs_dir / f"{date_str}.daily.md"
        if not path.exists():
            return None
        return {
            "date": date_str,
            "path": str(path),
            "markdown": path.read_text(encoding="utf-8"),
        }

    def get_metrics(self) -> dict[str, Any]:
        latest_brief = next(iter(self.list_briefs()), None)
        items = self._row("SELECT COUNT(*) AS count FROM items") or {"count": 0}
        clusters = self._row("SELECT COUNT(*) AS count FROM clusters") or {"count": 0}
        topics = self._row("SELECT COUNT(*) AS count FROM topic_profiles") or {"count": 0}
        fresh_items = self._row(
            "SELECT COUNT(*) AS count FROM items WHERE datetime(COALESCE(published_at, fetched_at)) >= datetime('now', '-7 days')"
        ) or {"count": 0}
        top_sources = self._rows(
            """
            SELECT source_name, COUNT(*) AS count
            FROM items
            WHERE datetime(COALESCE(published_at, fetched_at)) >= datetime('now', '-7 days')
            GROUP BY source_name
            ORDER BY count DESC, source_name ASC
            LIMIT 5
            """
        )
        return {
            "brief_count": len(self.list_briefs()),
            "latest_brief_date": latest_brief["date"] if latest_brief else None,
            "item_count": int(items["count"]),
            "cluster_count": int(clusters["count"]),
            "topic_count": int(topics["count"]),
            "items_last_7d": int(fresh_items["count"]),
            "top_sources_last_7d": top_sources,
        }

    def get_trending_topics(self, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT topic_id, name, kind, count_1d, count_3d, count_7d, count_30d, momentum, last_seen_at
            FROM topic_profiles
            WHERE datetime(COALESCE(last_seen_at, created_at)) >= datetime('now', ?)
            ORDER BY momentum DESC, last_seen_at DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", int(limit)),
        )

    def get_trend_clusters(self, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT cluster_id, label, trend_score, velocity_1d, velocity_3d, velocity_7d,
                   sources_count, representative_title, representative_url, last_seen_at
            FROM clusters
            WHERE datetime(COALESCE(last_seen_at, created_at)) >= datetime('now', ?)
            ORDER BY trend_score DESC, last_seen_at DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", int(limit)),
        )

    def search_items(self, query: str, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
        like = f"%{(query or '').strip().lower()}%"
        return self._rows(
            """
            SELECT item_id, title, url, source_name, source_category, published_at, fetched_at,
                   score, score_opportunity, tags_json, summary
            FROM items
            WHERE datetime(COALESCE(published_at, fetched_at)) >= datetime('now', ?)
              AND (
                lower(title) LIKE ? OR lower(COALESCE(summary, '')) LIKE ? OR
                lower(COALESCE(source_name, '')) LIKE ? OR lower(COALESCE(tags_json, '')) LIKE ?
              )
            ORDER BY score DESC, datetime(COALESCE(published_at, fetched_at)) DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", like, like, like, like, int(limit)),
        )

    def get_cluster_members(self, cluster_id: str, limit: int = 12) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT i.item_id, i.title, i.url, i.source_name, i.source_category, i.published_at, i.score, m.similarity
            FROM cluster_memberships m
            JOIN items i ON i.item_id = m.item_id
            WHERE m.cluster_id = ?
            ORDER BY i.score DESC, datetime(COALESCE(i.published_at, i.fetched_at)) DESC
            LIMIT ?
            """,
            (cluster_id, int(limit)),
        )

    def get_related_stories(self, query: str, days: int = 30, limit: int = 12) -> dict[str, Any]:
        matches = self.search_items(query=query, days=days, limit=5)
        if not matches:
            return {"query": query, "matches": [], "related": []}
        top = matches[0]
        item_row = self._row("SELECT cluster_id FROM cluster_memberships WHERE item_id = ?", (top["item_id"],))
        related: list[dict[str, Any]] = []
        cluster = None
        if item_row:
            cluster = self._row(
                "SELECT cluster_id, label, trend_score, representative_title, representative_url FROM clusters WHERE cluster_id = ?",
                (item_row["cluster_id"],),
            )
            related = self.get_cluster_members(item_row["cluster_id"], limit=limit)
        return {"query": query, "matches": matches, "cluster": cluster, "related": related}

    def get_news_about(self, entity: str, days: int = 7, limit: int = 20) -> dict[str, Any]:
        items = self.search_items(query=entity, days=days, limit=limit)
        clusters = self._rows(
            """
            SELECT cluster_id, label, trend_score, representative_title, representative_url, last_seen_at
            FROM clusters
            WHERE datetime(COALESCE(last_seen_at, created_at)) >= datetime('now', ?)
              AND (
                lower(COALESCE(label, '')) LIKE ? OR lower(COALESCE(representative_title, '')) LIKE ?
              )
            ORDER BY trend_score DESC, last_seen_at DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", f"%{entity.lower()}%", f"%{entity.lower()}%", min(int(limit), 10)),
        )
        return {"entity": entity, "items": items, "clusters": clusters}

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "get_trending_topics":
            return {"tool": tool_name, "result": self.get_trending_topics(**arguments)}
        if tool_name == "get_trend_clusters":
            return {"tool": tool_name, "result": self.get_trend_clusters(**arguments)}
        if tool_name == "search_items":
            return {"tool": tool_name, "result": self.search_items(**arguments)}
        if tool_name == "get_related_stories":
            return {"tool": tool_name, "result": self.get_related_stories(**arguments)}
        if tool_name == "get_news_about":
            return {"tool": tool_name, "result": self.get_news_about(**arguments)}
        raise ValueError(f"Unsupported tool: {tool_name}")


def serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        if "tags_json" in data:
            try:
                data["tags"] = json.loads(data.pop("tags_json") or "[]")
            except Exception:
                data["tags"] = []
        out.append(data)
    return out
