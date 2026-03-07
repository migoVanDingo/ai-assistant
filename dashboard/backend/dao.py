"""Data access layer for the Morning Brief dashboard."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from briefbot.resolve import rank_items_for_query


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
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dashboard_queries (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_query TEXT NOT NULL,
                llm_response_md TEXT NOT NULL,
                tool_name TEXT,
                tool_args_json TEXT,
                tool_result_json TEXT,
                error TEXT,
                llm_provider TEXT,
                llm_model TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_dashboard_queries_created_at
            ON dashboard_queries(created_at DESC);

            CREATE TABLE IF NOT EXISTS dashboard_story_feedback (
                item_id TEXT PRIMARY KEY,
                vote INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dashboard_story_feedback_events (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                section TEXT NOT NULL,
                signal REAL NOT NULL,
                source_name TEXT,
                cluster_id TEXT,
                tags_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_story_feedback_events_created_at
            ON dashboard_story_feedback_events(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_story_feedback_events_item_id
            ON dashboard_story_feedback_events(item_id);
            """
        )
        self.conn.commit()

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

    def _cleanup_query_history(self, days: int = 14, limit: int = 20) -> None:
        max_days = max(1, int(days))
        max_limit = max(1, min(int(limit), 20))
        self.conn.execute(
            """
            DELETE FROM dashboard_queries
            WHERE datetime(created_at) < datetime('now', ?)
            """,
            (f"-{max_days} days",),
        )
        rows = self.conn.execute(
            "SELECT id FROM dashboard_queries ORDER BY datetime(created_at) DESC"
        ).fetchall()
        if len(rows) > max_limit:
            stale_ids = [row["id"] for row in rows[max_limit:]]
            self.conn.executemany("DELETE FROM dashboard_queries WHERE id = ?", [(query_id,) for query_id in stale_ids])
        self.conn.commit()

    def record_query(
        self,
        *,
        user_query: str,
        llm_response_md: str,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
        error: str | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        query_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO dashboard_queries(
                id, created_at, user_query, llm_response_md, tool_name, tool_args_json,
                tool_result_json, error, llm_provider, llm_model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                created_at,
                user_query,
                llm_response_md,
                tool_name,
                json.dumps(tool_args) if tool_args is not None else None,
                json.dumps(tool_result) if tool_result is not None else None,
                error,
                llm_provider,
                llm_model,
            ),
        )
        self.conn.commit()
        self._cleanup_query_history(days=14, limit=20)
        return self.get_query_history_entry(query_id) or {
            "id": query_id,
            "created_at": created_at,
            "user_query": user_query,
            "llm_response_md": llm_response_md,
        }

    def list_query_history(self, days: int = 14, limit: int = 20) -> list[dict[str, Any]]:
        self._cleanup_query_history(days=days, limit=limit)
        rows = self._rows(
            """
            SELECT id, created_at, user_query, llm_response_md, error
            FROM dashboard_queries
            WHERE datetime(created_at) >= datetime('now', ?)
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (f"-{max(1, int(days))} days", min(max(1, int(limit)), 20)),
        )
        for row in rows:
            preview = (row.get("llm_response_md") or "").strip().replace("\n", " ")
            row["response_preview"] = (preview[:157] + "...") if len(preview) > 160 else preview
        return rows

    def get_query_history_entry(self, query_id: str) -> dict[str, Any] | None:
        row = self._row(
            """
            SELECT *
            FROM dashboard_queries
            WHERE id = ?
            """,
            (query_id,),
        )
        if not row:
            return None
        row["tool_args"] = _json_loads(row.pop("tool_args_json", None), {})
        row["tool_result"] = _json_loads(row.pop("tool_result_json", None), None)
        return row

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
        query_text = (query or "").strip().lower()
        list_all = query_text in {"", "all", "all items", "all stories", "everything", "latest items"}
        like = f"%{query_text}%"
        sql = """
            SELECT item_id, title, url, canonical_url, source_name, source_category, published_at, fetched_at,
                   score, score_opportunity, tags_json, summary, watch_hits_json
            FROM items
            WHERE datetime(COALESCE(published_at, fetched_at)) >= datetime('now', ?)
        """
        params: list[Any] = [f"-{int(days)} days"]
        if not list_all:
            sql += """
              AND (
                lower(title) LIKE ? OR lower(COALESCE(summary, '')) LIKE ? OR
                lower(COALESCE(source_name, '')) LIKE ? OR lower(COALESCE(tags_json, '')) LIKE ?
              )
            """
            params.extend([like, like, like, like])
        sql += """
            ORDER BY score DESC, datetime(COALESCE(published_at, fetched_at)) DESC
            LIMIT ?
        """
        params.append(int(limit))
        return self._rows(sql, tuple(params))

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

    def find_best_item_for_query(self, query: str, days: int = 365, limit: int = 25) -> dict[str, Any] | None:
        candidates = self.search_items(query=query, days=days, limit=limit)
        if not candidates:
            return None
        ranked = rank_items_for_query(query, serialize_rows(candidates))
        return ranked[0] if ranked else None

    def list_source_names(self) -> list[str]:
        rows = self._rows(
            """
            SELECT DISTINCT source_name
            FROM items
            WHERE source_name IS NOT NULL AND trim(source_name) != ''
            ORDER BY source_name COLLATE NOCASE ASC
            """
        )
        return [row["source_name"] for row in rows]

    def list_clusters(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._rows(
            """
            SELECT cluster_id AS id, label, trend_score
            FROM clusters
            ORDER BY trend_score DESC, label ASC
            LIMIT ?
            """,
            (max(int(limit) * 4, 200),),
        )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            label = (row.get("label") or "").strip()
            key = label.lower() if label else f"id:{row.get('id')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
            if len(deduped) >= int(limit):
                break
        return deduped

    def list_tags(self, days: int = 30, limit: int = 200) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT lower(trim(json_each.value)) AS tag, COUNT(*) AS count
            FROM items, json_each(items.tags_json)
            WHERE json_each.value IS NOT NULL
              AND trim(json_each.value) != ''
              AND datetime(COALESCE(items.published_at, items.fetched_at)) >= datetime('now', ?)
            GROUP BY lower(trim(json_each.value))
            ORDER BY count DESC, tag ASC
            LIMIT ?
            """,
            (f"-{int(days)} days", int(limit)),
        )

    def list_watch_hits(self, days: int = 30, limit: int = 200) -> list[dict[str, Any]]:
        return self._rows(
            """
            SELECT trim(json_each.value) AS watch_hit, COUNT(*) AS count
            FROM items, json_each(COALESCE(items.watch_hits_json, '[]'))
            WHERE json_each.value IS NOT NULL
              AND trim(json_each.value) != ''
              AND datetime(COALESCE(items.published_at, items.fetched_at)) >= datetime('now', ?)
            GROUP BY trim(json_each.value)
            ORDER BY count DESC, watch_hit COLLATE NOCASE ASC
            LIMIT ?
            """,
            (f"-{int(days)} days", int(limit)),
        )

    def query_stories(
        self,
        *,
        source_name: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 20,
        cluster_id: str | None = None,
        tags: list[str] | None = None,
        watch_hits: list[str] | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        safe_limit = min(50, max(5, int(limit)))
        safe_order = "ASC" if str(order).lower() == "asc" else "DESC"

        clauses = ["1=1"]
        params: list[Any] = []

        if source_name:
            clauses.append("i.source_name = ?")
            params.append(source_name)
        if from_date:
            clauses.append("date(COALESCE(i.published_at, i.fetched_at)) >= date(?)")
            params.append(from_date)
        if to_date:
            clauses.append("date(COALESCE(i.published_at, i.fetched_at)) <= date(?)")
            params.append(to_date)
        if cluster_id:
            clauses.append("m.cluster_id = ?")
            params.append(cluster_id)
        for tag in tags or []:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(i.tags_json) jt WHERE lower(trim(jt.value)) = lower(?))"
            )
            params.append(tag)
        for watch_hit in watch_hits or []:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(COALESCE(i.watch_hits_json, '[]')) jw WHERE trim(jw.value) = ?)"
            )
            params.append(watch_hit)

        rows = self._rows(
            f"""
            SELECT DISTINCT
                i.item_id,
                i.title,
                i.url,
                i.canonical_url,
                i.published_at,
                i.fetched_at,
                i.source_name,
                i.summary,
                i.tags_json,
                i.watch_hits_json,
                m.cluster_id
            FROM items i
            LEFT JOIN cluster_memberships m ON m.item_id = i.item_id
            WHERE {' AND '.join(clauses)}
            ORDER BY datetime(COALESCE(i.published_at, i.fetched_at)) {safe_order}, i.title COLLATE NOCASE ASC
            LIMIT ?
            """,
            tuple(params + [safe_limit]),
        )
        items = serialize_rows(rows)
        feedback_map = self.get_story_feedback_map([item.get("item_id") for item in items if item.get("item_id")])
        self._attach_feedback(items, feedback_map)
        return {
            "filters": {
                "source_name": source_name,
                "from_date": from_date,
                "to_date": to_date,
                "limit": safe_limit,
                "cluster_id": cluster_id,
                "tags": list(tags or []),
                "watch_hits": list(watch_hits or []),
                "order": "asc" if safe_order == "ASC" else "desc",
            },
            "items": items,
        }

    def list_story_sections(
        self,
        *,
        section_limit: int = 12,
        top_days: int = 2,
        trending_days: int = 7,
        suggested_days: int = 7,
        other_days: int = 7,
    ) -> dict[str, list[dict[str, Any]]]:
        safe_limit = min(25, max(5, int(section_limit)))
        top_rows = self._rows(
            """
            SELECT DISTINCT
                i.item_id, i.title, i.url, i.canonical_url, i.published_at, i.fetched_at,
                i.source_name, i.summary, i.score, i.tags_json, i.watch_hits_json, m.cluster_id
            FROM items i
            LEFT JOIN cluster_memberships m ON m.item_id = i.item_id
            WHERE datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime('now', ?)
            ORDER BY i.score DESC, datetime(COALESCE(i.published_at, i.fetched_at)) DESC
            LIMIT ?
            """,
            (f"-{max(1, int(top_days))} days", safe_limit),
        )
        trending_rows = self._rows(
            """
            SELECT
                i.item_id, i.title, i.url, i.canonical_url, i.published_at, i.fetched_at,
                i.source_name, i.summary, i.score, i.tags_json, i.watch_hits_json, m.cluster_id,
                c.trend_score
            FROM items i
            JOIN cluster_memberships m ON m.item_id = i.item_id
            JOIN clusters c ON c.cluster_id = m.cluster_id
            WHERE datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime('now', ?)
              AND datetime(COALESCE(c.last_seen_at, c.created_at)) >= datetime('now', ?)
            ORDER BY c.trend_score DESC, i.score DESC, datetime(COALESCE(i.published_at, i.fetched_at)) DESC
            LIMIT ?
            """,
            (f"-{max(1, int(trending_days))} days", f"-{max(1, int(trending_days))} days", safe_limit * 3),
        )
        trending_items = self._dedupe_items_preserve_order(serialize_rows(trending_rows), limit=safe_limit)

        other_rows = self._rows(
            """
            SELECT DISTINCT
                i.item_id, i.title, i.url, i.canonical_url, i.published_at, i.fetched_at,
                i.source_name, i.summary, i.score, i.tags_json, i.watch_hits_json, m.cluster_id
            FROM items i
            LEFT JOIN cluster_memberships m ON m.item_id = i.item_id
            WHERE datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime('now', ?)
            ORDER BY datetime(COALESCE(i.published_at, i.fetched_at)) DESC, i.score DESC
            LIMIT ?
            """,
            (f"-{max(1, int(other_days))} days", safe_limit),
        )
        suggested_items = self._compute_suggested_links(days=suggested_days, limit=safe_limit)

        sections = {
            "top_links": serialize_rows(top_rows),
            "trending": trending_items,
            "suggested_links": suggested_items,
            "other_links": serialize_rows(other_rows),
        }
        all_items: list[dict[str, Any]] = []
        for values in sections.values():
            all_items.extend(values)
        feedback_map = self.get_story_feedback_map([item.get("item_id") for item in all_items if item.get("item_id")])
        for values in sections.values():
            self._attach_feedback(values, feedback_map)
        return sections

    def get_story_feedback_map(self, item_ids: list[str]) -> dict[str, dict[str, Any]]:
        unique_ids = sorted({str(item_id) for item_id in item_ids if item_id})
        if not unique_ids:
            return {}
        placeholders = ",".join(["?"] * len(unique_ids))
        rows = self._rows(
            f"""
            SELECT item_id, vote, score, updated_at
            FROM dashboard_story_feedback
            WHERE item_id IN ({placeholders})
            """,
            tuple(unique_ids),
        )
        out = {row["item_id"]: row for row in rows}
        for item_id in unique_ids:
            out.setdefault(item_id, {"item_id": item_id, "vote": 0, "score": 0.0, "updated_at": None})
        return out

    def set_story_feedback(self, *, item_id: str, vote: int, section: str) -> dict[str, Any]:
        safe_vote = int(vote)
        if safe_vote not in (-1, 0, 1):
            raise ValueError("vote must be -1, 0, or 1")
        safe_section = (section or "other_links").strip().lower() or "other_links"
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        row = self._row(
            """
            SELECT vote, score
            FROM dashboard_story_feedback
            WHERE item_id = ?
            """,
            (item_id,),
        )
        prev_vote = int((row or {}).get("vote") or 0)
        prev_score = float((row or {}).get("score") or 0.0)
        delta_vote = safe_vote - prev_vote
        new_score = prev_score + delta_vote

        item = self._row(
            """
            SELECT i.item_id, i.source_name, i.tags_json, m.cluster_id
            FROM items i
            LEFT JOIN cluster_memberships m ON m.item_id = i.item_id
            WHERE i.item_id = ?
            """,
            (item_id,),
        )
        if not item:
            raise ValueError("item not found")

        self.conn.execute(
            """
            INSERT INTO dashboard_story_feedback(item_id, vote, score, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
              vote=excluded.vote,
              score=excluded.score,
              updated_at=excluded.updated_at
            """,
            (item_id, safe_vote, new_score, now),
        )

        if delta_vote != 0:
            section_weight = self._section_feedback_weight(safe_section)
            signal = float(delta_vote) * section_weight
            self.conn.execute(
                """
                INSERT INTO dashboard_story_feedback_events(
                    id, item_id, section, signal, source_name, cluster_id, tags_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    item_id,
                    safe_section,
                    signal,
                    item.get("source_name"),
                    item.get("cluster_id"),
                    item.get("tags_json"),
                    now,
                ),
            )
        self.conn.commit()
        return {
            "item_id": item_id,
            "vote": safe_vote,
            "score": new_score,
            "updated_at": now,
        }

    def _attach_feedback(self, items: list[dict[str, Any]], feedback_map: dict[str, dict[str, Any]]) -> None:
        for item in items:
            state = feedback_map.get(item.get("item_id")) or {"vote": 0, "score": 0.0}
            item["feedback_vote"] = int(state.get("vote") or 0)
            item["feedback_score"] = float(state.get("score") or 0.0)
            item["feedback_updated_at"] = state.get("updated_at")

    def _section_feedback_weight(self, section: str) -> float:
        return 3.0 if section == "suggested_links" else 1.0

    def _load_preference_profile(self, max_age_days: int = 60) -> dict[str, dict[str, float]]:
        rows = self._rows(
            """
            SELECT source_name, cluster_id, tags_json, signal
            FROM dashboard_story_feedback_events
            WHERE datetime(created_at) >= datetime('now', ?)
            ORDER BY datetime(created_at) DESC
            """,
            (f"-{max(7, int(max_age_days))} days",),
        )
        source_scores: dict[str, float] = {}
        cluster_scores: dict[str, float] = {}
        tag_scores: dict[str, float] = {}
        for row in rows:
            signal = float(row.get("signal") or 0.0)
            source_name = (row.get("source_name") or "").strip().lower()
            cluster_id = (row.get("cluster_id") or "").strip()
            if source_name:
                source_scores[source_name] = source_scores.get(source_name, 0.0) + signal
            if cluster_id:
                cluster_scores[cluster_id] = cluster_scores.get(cluster_id, 0.0) + signal
            for raw_tag in _json_loads(row.get("tags_json"), []):
                tag = str(raw_tag).strip().lower()
                if not tag:
                    continue
                tag_scores[tag] = tag_scores.get(tag, 0.0) + signal
        return {"source": source_scores, "cluster": cluster_scores, "tag": tag_scores}

    def _compute_suggested_links(self, *, days: int = 7, limit: int = 12) -> list[dict[str, Any]]:
        profile = self._load_preference_profile(max_age_days=60)
        rows = self._rows(
            """
            SELECT DISTINCT
                i.item_id, i.title, i.url, i.canonical_url, i.published_at, i.fetched_at,
                i.source_name, i.summary, i.score, i.tags_json, i.watch_hits_json, m.cluster_id
            FROM items i
            LEFT JOIN cluster_memberships m ON m.item_id = i.item_id
            WHERE datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime('now', ?)
            ORDER BY datetime(COALESCE(i.published_at, i.fetched_at)) DESC, i.score DESC
            LIMIT ?
            """,
            (f"-{max(1, int(days))} days", max(int(limit) * 12, 80)),
        )
        items = serialize_rows(rows)
        if not items:
            return []
        state_map = self.get_story_feedback_map([item.get("item_id") for item in items if item.get("item_id")])

        scored: list[dict[str, Any]] = []
        for item in items:
            item_id = item.get("item_id")
            if not item_id:
                continue
            feedback_state = state_map.get(item_id) or {"vote": 0}
            if int(feedback_state.get("vote") or 0) < 0:
                continue
            source_key = str(item.get("source_name") or "").strip().lower()
            cluster_key = str(item.get("cluster_id") or "").strip()
            tag_keys = [str(tag).strip().lower() for tag in item.get("tags") or [] if str(tag).strip()]
            pref_score = 0.0
            pref_score += profile["source"].get(source_key, 0.0) * 0.45
            pref_score += profile["cluster"].get(cluster_key, 0.0) * 0.35
            if tag_keys:
                pref_score += sum(profile["tag"].get(tag, 0.0) for tag in tag_keys) * 0.20 / len(tag_keys)
            base_score = float(item.get("score") or 0.0)
            item["suggested_score"] = round((pref_score * 2.0) + (base_score * 0.25), 4)
            scored.append(item)

        scored.sort(
            key=lambda item: (
                float(item.get("suggested_score") or 0.0),
                float(item.get("score") or 0.0),
                str(item.get("published_at") or item.get("fetched_at") or ""),
            ),
            reverse=True,
        )
        return self._dedupe_items_preserve_order(scored, limit=limit)

    def _dedupe_items_preserve_order(self, items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            item_id = str(item.get("item_id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            out.append(item)
            if len(out) >= int(limit):
                break
        return out

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
        if tool_name == "find_best_item_for_query":
            return {"tool": tool_name, "result": self.find_best_item_for_query(**arguments)}
        raise ValueError(f"Unsupported tool: {tool_name}")


def serialize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        if "tags_json" in data:
            data["tags"] = _json_loads(data.pop("tags_json"), [])
        if "watch_hits_json" in data:
            data["watch_hits"] = _json_loads(data.pop("watch_hits_json"), [])
        out.append(data)
    return out


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default
