"""SQLite persistence for feed cache, discovery cache, items, and radar clusters.

Core responsibilities:
- initialize schema and apply additive migrations
- cache discovery/feed headers (ETag/Last-Modified)
- upsert items with dedupe behavior
- store and query clusters/memberships/events for radar views
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .util import ensure_dir, json_dumps, utc_now_iso


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS discovered_feeds (
    site_url TEXT NOT NULL PRIMARY KEY,
    feeds_json TEXT NOT NULL,
    discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_cache (
    feed_url TEXT NOT NULL PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_checked_at TEXT
);

CREATE TABLE IF NOT EXISTS items (
    item_id TEXT NOT NULL PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    canonical_url TEXT,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    author TEXT,
    summary TEXT,
    tags_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    metrics_json TEXT,
    score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_id TEXT NOT NULL PRIMARY KEY,
    label TEXT,
    created_at TEXT NOT NULL,
    first_seen_at TEXT,
    last_seen_at TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    sources_count INTEGER NOT NULL DEFAULT 0,
    categories TEXT,
    top_tokens TEXT,
    velocity_7d INTEGER NOT NULL DEFAULT 0,
    velocity_3d INTEGER NOT NULL DEFAULT 0,
    velocity_1d INTEGER NOT NULL DEFAULT 0,
    diversity_score REAL NOT NULL DEFAULT 0.0,
    trend_score REAL NOT NULL DEFAULT 0.0,
    representative_url TEXT,
    representative_title TEXT
);

CREATE TABLE IF NOT EXISTS cluster_memberships (
    item_id TEXT NOT NULL PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    similarity REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS cluster_events (
    cluster_id TEXT NOT NULL,
    date TEXT NOT NULL,
    items_added INTEGER NOT NULL DEFAULT 0,
    sources_added INTEGER NOT NULL DEFAULT 0,
    top_item_id TEXT,
    PRIMARY KEY (cluster_id, date)
);

CREATE TABLE IF NOT EXISTS summaries (
    item_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    summary_md TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (item_id, provider, model)
);

CREATE TABLE IF NOT EXISTS topic_profiles (
    topic_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    first_seen_at TEXT,
    last_seen_at TEXT,
    count_1d INTEGER DEFAULT 0,
    count_3d INTEGER DEFAULT 0,
    count_7d INTEGER DEFAULT 0,
    count_30d INTEGER DEFAULT 0,
    momentum REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_fetched_at ON items(fetched_at);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_source_id ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC);
CREATE INDEX IF NOT EXISTS idx_memberships_cluster_id ON cluster_memberships(cluster_id);
CREATE INDEX IF NOT EXISTS idx_clusters_trend_score ON clusters(trend_score DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_item_id ON summaries(item_id);
CREATE INDEX IF NOT EXISTS idx_topic_profiles_momentum ON topic_profiles(momentum DESC, last_seen_at DESC);
"""


ITEM_ADDITIONAL_COLUMNS: list[tuple[str, str]] = [
    ("source_category", "TEXT"),
    ("source_tier", "INTEGER"),
    ("source_max_daily", "INTEGER"),
    ("watch_hits_json", "TEXT"),
    ("score_opportunity", "REAL"),
    ("opportunity_reason", "TEXT"),
    ("opportunity_tags_json", "TEXT"),
]


SUMMARY_ADDITIONAL_COLUMNS: list[tuple[str, str]] = []


@dataclass
class UpsertResult:
    inserted: bool = False
    duplicate: bool = False


class Store:
    def __init__(self, db_path: str | Path = "data/briefbot.db") -> None:
        db_path = Path(db_path)
        ensure_dir(db_path.parent)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        self._apply_migrations()
        self.conn.commit()

    def _apply_migrations(self) -> None:
        self._ensure_item_columns()

    def _ensure_item_columns(self) -> None:
        rows = self.conn.execute("PRAGMA table_info(items)").fetchall()
        existing = {row["name"] for row in rows}
        for col_name, col_type in ITEM_ADDITIONAL_COLUMNS:
            if col_name not in existing:
                self.conn.execute(f"ALTER TABLE items ADD COLUMN {col_name} {col_type}")

    def close(self) -> None:
        self.conn.close()

    def get_discovered_feeds(self, site_url: str, max_age_days: int = 7) -> list[str] | None:
        q = """
        SELECT feeds_json FROM discovered_feeds
        WHERE site_url = ?
          AND julianday('now') - julianday(discovered_at) <= ?
        """
        row = self.conn.execute(q, (site_url, max_age_days)).fetchone()
        if not row:
            return None
        return json.loads(row["feeds_json"])

    def set_discovered_feeds(self, site_url: str, feeds: list[str]) -> None:
        q = """
        INSERT INTO discovered_feeds(site_url, feeds_json, discovered_at)
        VALUES(?, ?, ?)
        ON CONFLICT(site_url) DO UPDATE SET
          feeds_json=excluded.feeds_json,
          discovered_at=excluded.discovered_at
        """
        self.conn.execute(q, (site_url, json_dumps(feeds), utc_now_iso()))
        self.conn.commit()

    def get_feed_cache_headers(self, feed_url: str) -> dict[str, str]:
        row = self.conn.execute(
            "SELECT etag, last_modified FROM feed_cache WHERE feed_url = ?", (feed_url,)
        ).fetchone()
        if not row:
            return {}
        headers: dict[str, str] = {}
        if row["etag"]:
            headers["If-None-Match"] = row["etag"]
        if row["last_modified"]:
            headers["If-Modified-Since"] = row["last_modified"]
        return headers

    def set_feed_cache_headers(self, feed_url: str, etag: str | None, last_modified: str | None) -> None:
        q = """
        INSERT INTO feed_cache(feed_url, etag, last_modified, last_checked_at)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(feed_url) DO UPDATE SET
          etag=excluded.etag,
          last_modified=excluded.last_modified,
          last_checked_at=excluded.last_checked_at
        """
        self.conn.execute(q, (feed_url, etag, last_modified, utc_now_iso()))
        self.conn.commit()

    def upsert_item(self, item: dict[str, Any], dry_run: bool = False) -> UpsertResult:
        now = utc_now_iso()
        row = self.conn.execute(
            "SELECT item_id FROM items WHERE dedupe_key = ?", (item["dedupe_key"],)
        ).fetchone()

        if row:
            if not dry_run:
                self.conn.execute(
                    """
                    UPDATE items
                    SET last_seen_at = ?, score = ?, fetched_at = ?,
                        source_category = ?, source_tier = ?, source_max_daily = ?, watch_hits_json = ?,
                        score_opportunity = ?, opportunity_reason = ?, opportunity_tags_json = ?
                    WHERE dedupe_key = ?
                    """,
                    (
                        now,
                        item["score"],
                        item["fetched_at"],
                        item.get("source_category"),
                        item.get("source_tier"),
                        item.get("source_max_daily"),
                        json_dumps(item.get("watch_hits", [])),
                        item.get("score_opportunity"),
                        item.get("opportunity_reason"),
                        json_dumps(item.get("opportunity_tags", [])),
                        item["dedupe_key"],
                    ),
                )
                self.conn.commit()
            return UpsertResult(inserted=False, duplicate=True)

        if dry_run:
            return UpsertResult(inserted=True, duplicate=False)

        q = """
        INSERT INTO items(
            item_id, dedupe_key, canonical_url, source_id, source_name, title, url,
            published_at, fetched_at, last_seen_at, author, summary, tags_json,
            raw_json, metrics_json, score, source_category, source_tier,
            source_max_daily, watch_hits_json, score_opportunity, opportunity_reason,
            opportunity_tags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(
            q,
            (
                item["item_id"],
                item["dedupe_key"],
                item.get("canonical_url"),
                item["source_id"],
                item["source_name"],
                item["title"],
                item.get("url"),
                item.get("published_at"),
                item["fetched_at"],
                now,
                item.get("author"),
                item.get("summary"),
                json_dumps(item.get("tags", [])),
                json_dumps(item.get("raw", {})),
                json_dumps(item.get("metrics")) if item.get("metrics") is not None else None,
                float(item.get("score", 0.0)),
                item.get("source_category"),
                item.get("source_tier"),
                item.get("source_max_daily"),
                json_dumps(item.get("watch_hits", [])),
                item.get("score_opportunity"),
                item.get("opportunity_reason"),
                json_dumps(item.get("opportunity_tags", [])),
            ),
        )
        self.conn.commit()
        return UpsertResult(inserted=True, duplicate=False)

    def _row_to_item(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "[]")
        item["raw"] = json.loads(item.pop("raw_json") or "{}")
        item["metrics"] = json.loads(item.pop("metrics_json")) if item.get("metrics_json") else {}
        item["watch_hits"] = json.loads(item.pop("watch_hits_json") or "[]")
        item["opportunity_tags"] = json.loads(item.pop("opportunity_tags_json") or "[]")
        return item

    def get_items_for_date(self, date_str: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM items
            WHERE date(fetched_at) = date(?)
            ORDER BY score DESC, published_at DESC
            LIMIT ?
            """,
            (date_str, limit),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def get_items_for_date_by_view(self, date_str: str, limit: int = 50, view: str = "highlights") -> list[dict[str, Any]]:
        if view == "opportunities":
            order_clause = "ORDER BY COALESCE(score_opportunity, score, 0) DESC, score DESC, published_at DESC"
        else:
            order_clause = "ORDER BY score DESC, published_at DESC"
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM items
            WHERE date(fetched_at) = date(?)
            {order_clause}
            LIMIT ?
            """,
            (date_str, limit),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def fetch_items_in_window(self, date_str: str, window_days: int = 14) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM items
            WHERE date(COALESCE(published_at, fetched_at))
                BETWEEN date(?, ?) AND date(?)
            ORDER BY datetime(COALESCE(published_at, fetched_at)) ASC, score DESC
            """,
            (date_str, f"-{int(window_days)} days", date_str),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def get_item_by_id(self, item_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def get_recent_items(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM items
            ORDER BY datetime(COALESCE(published_at, fetched_at)) DESC, score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def search_items(
        self,
        query: str,
        date_str: str | None = None,
        limit: int = 50,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        like = f"%{query.strip().lower()}%"
        params: list[Any] = [like, like, like, like]
        where = [
            "(lower(title) LIKE ? OR lower(COALESCE(summary,'')) LIKE ? OR "
            "lower(COALESCE(source_name,'')) LIKE ? OR lower(COALESCE(tags_json,'')) LIKE ?)"
        ]
        if date_str:
            where.append("date(fetched_at) = date(?)")
            params.append(date_str)
        params.append(limit * 8)

        rows = self.conn.execute(
            f"""
            SELECT *
            FROM items
            WHERE {' AND '.join(where)}
            ORDER BY score DESC, datetime(COALESCE(published_at, fetched_at)) DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        items = [self._row_to_item(row) for row in rows]
        include = {t.lower() for t in (include_tags or [])}
        exclude = {t.lower() for t in (exclude_tags or [])}
        if not include and not exclude:
            return items

        out: list[dict[str, Any]] = []
        for item in items:
            tags = {str(t).lower() for t in item.get("tags", [])}
            if include and not (tags & include):
                continue
            if exclude and (tags & exclude):
                continue
            out.append(item)
        return out

    def clear_memberships_in_window(self, date_str: str, window_days: int) -> None:
        self.conn.execute(
            """
            DELETE FROM cluster_memberships
            WHERE item_id IN (
                SELECT item_id
                FROM items
                WHERE date(COALESCE(published_at, fetched_at))
                    BETWEEN date(?, ?) AND date(?)
            )
            """,
            (date_str, f"-{int(window_days)} days", date_str),
        )
        self.conn.commit()

    def upsert_membership(self, item_id: str, cluster_id: str, similarity: float, assigned_at: str | None = None) -> None:
        q = """
        INSERT INTO cluster_memberships(item_id, cluster_id, assigned_at, similarity)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
          cluster_id=excluded.cluster_id,
          assigned_at=excluded.assigned_at,
          similarity=excluded.similarity
        """
        self.conn.execute(q, (item_id, cluster_id, assigned_at or utc_now_iso(), float(similarity)))
        self.conn.commit()

    def upsert_cluster(self, cluster: dict[str, Any]) -> None:
        q = """
        INSERT INTO clusters(
            cluster_id, label, created_at, first_seen_at, last_seen_at,
            item_count, sources_count, categories, top_tokens,
            velocity_7d, velocity_3d, velocity_1d,
            diversity_score, trend_score,
            representative_url, representative_title
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cluster_id) DO UPDATE SET
          label=excluded.label,
          first_seen_at=excluded.first_seen_at,
          last_seen_at=excluded.last_seen_at,
          item_count=excluded.item_count,
          sources_count=excluded.sources_count,
          categories=excluded.categories,
          top_tokens=excluded.top_tokens,
          velocity_7d=excluded.velocity_7d,
          velocity_3d=excluded.velocity_3d,
          velocity_1d=excluded.velocity_1d,
          diversity_score=excluded.diversity_score,
          trend_score=excluded.trend_score,
          representative_url=excluded.representative_url,
          representative_title=excluded.representative_title
        """
        self.conn.execute(
            q,
            (
                cluster["cluster_id"],
                cluster.get("label"),
                cluster.get("created_at") or utc_now_iso(),
                cluster.get("first_seen_at"),
                cluster.get("last_seen_at"),
                int(cluster.get("item_count", 0)),
                int(cluster.get("sources_count", 0)),
                json_dumps(cluster.get("categories", [])),
                json_dumps(cluster.get("top_tokens", [])),
                int(cluster.get("velocity_7d", 0)),
                int(cluster.get("velocity_3d", 0)),
                int(cluster.get("velocity_1d", 0)),
                float(cluster.get("diversity_score", 0.0)),
                float(cluster.get("trend_score", 0.0)),
                cluster.get("representative_url"),
                cluster.get("representative_title"),
            ),
        )
        self.conn.commit()

    def upsert_cluster_event(
        self,
        cluster_id: str,
        date_str: str,
        items_added: int,
        sources_added: int,
        top_item_id: str | None,
    ) -> None:
        q = """
        INSERT INTO cluster_events(cluster_id, date, items_added, sources_added, top_item_id)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(cluster_id, date) DO UPDATE SET
          items_added=excluded.items_added,
          sources_added=excluded.sources_added,
          top_item_id=excluded.top_item_id
        """
        self.conn.execute(q, (cluster_id, date_str, int(items_added), int(sources_added), top_item_id))
        self.conn.commit()

    def fetch_clusters_for_date(self, date_str: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM clusters
            WHERE date(last_seen_at) <= date(?)
            ORDER BY trend_score DESC, last_seen_at DESC
            LIMIT ?
            """,
            (date_str, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            cluster = dict(row)
            cluster["categories"] = json.loads(cluster.get("categories") or "[]")
            cluster["top_tokens"] = json.loads(cluster.get("top_tokens") or "[]")
            out.append(cluster)
        return out

    def fetch_cluster_members(
        self,
        cluster_id: str,
        limit: int = 100,
        include_old: bool = True,
        since_iso: str | None = None,
    ) -> list[dict[str, Any]]:
        where_parts = ["m.cluster_id = ?"]
        params: list[Any] = [cluster_id]
        if since_iso:
            where_parts.append("datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime(?)")
            params.append(since_iso)
        if not include_old:
            where_parts.append("date(COALESCE(i.published_at, i.fetched_at)) = date('now')")

        rows = self.conn.execute(
            f"""
            SELECT i.*, m.similarity
            FROM cluster_memberships m
            JOIN items i ON i.item_id = m.item_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY score DESC, datetime(COALESCE(i.published_at, i.fetched_at)) DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [self._row_to_item(row) | {"similarity": row["similarity"]} for row in rows]

    def get_cluster_for_item(self, item_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT cluster_id FROM cluster_memberships WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        return row["cluster_id"] if row else None

    def get_cluster(self, cluster_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM clusters WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["categories"] = json.loads(data.get("categories") or "[]")
        data["top_tokens"] = json.loads(data.get("top_tokens") or "[]")
        return data

    def get_followup_candidates(self, date_str: str) -> list[dict[str, Any]]:
        end_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        since_24h = (end_dt - timedelta(days=1)).isoformat()
        older_than = (end_dt - timedelta(days=3)).isoformat()

        rows = self.conn.execute(
            """
            SELECT c.*, i.item_id, i.title, i.url, i.score, i.published_at, i.source_name
            FROM cluster_memberships m
            JOIN clusters c ON c.cluster_id = m.cluster_id
            JOIN items i ON i.item_id = m.item_id
            WHERE datetime(COALESCE(i.published_at, i.fetched_at)) >= datetime(?)
              AND datetime(c.first_seen_at) < datetime(?)
            ORDER BY c.trend_score DESC, datetime(COALESCE(i.published_at, i.fetched_at)) DESC
            """,
            (since_24h, older_than),
        ).fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["categories"] = json.loads(data.get("categories") or "[]")
            data["top_tokens"] = json.loads(data.get("top_tokens") or "[]")
            out.append(data)
        return out

    def purge_stale_clusters(self, cutoff_date: str) -> None:
        # Keep cluster table bounded by removing clusters that have no members after cutoff.
        self.conn.execute(
            """
            DELETE FROM clusters
            WHERE cluster_id NOT IN (
              SELECT DISTINCT m.cluster_id
              FROM cluster_memberships m
              JOIN items i ON i.item_id = m.item_id
              WHERE date(COALESCE(i.published_at, i.fetched_at)) >= date(?)
            )
            """,
            (cutoff_date,),
        )
        self.conn.commit()

    def upsert_topic_profile(self, profile: dict[str, Any]) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO topic_profiles(
                topic_id, name, kind, first_seen_at, last_seen_at,
                count_1d, count_3d, count_7d, count_30d, momentum,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                name=excluded.name,
                kind=excluded.kind,
                first_seen_at=excluded.first_seen_at,
                last_seen_at=excluded.last_seen_at,
                count_1d=excluded.count_1d,
                count_3d=excluded.count_3d,
                count_7d=excluded.count_7d,
                count_30d=excluded.count_30d,
                momentum=excluded.momentum,
                updated_at=excluded.updated_at
            """,
            (
                profile["topic_id"],
                profile["name"],
                profile["kind"],
                profile.get("first_seen_at"),
                profile.get("last_seen_at"),
                int(profile.get("count_1d", 0)),
                int(profile.get("count_3d", 0)),
                int(profile.get("count_7d", 0)),
                int(profile.get("count_30d", 0)),
                float(profile.get("momentum", 0.0)),
                profile.get("created_at") or now,
                now,
            ),
        )
        self.conn.commit()

    def fetch_top_topics(
        self,
        date_str: str,
        limit: int = 50,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        where = ["date(COALESCE(last_seen_at, created_at)) <= date(?)"]
        params: list[Any] = [date_str]
        if kind:
            where.append("kind = ?")
            params.append(kind)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM topic_profiles
            WHERE {' AND '.join(where)}
            ORDER BY momentum DESC, last_seen_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_summary(self, item_id: str, provider: str | None = None, model: str | None = None) -> dict[str, Any] | None:
        if provider and model:
            row = self.conn.execute(
                """
                SELECT *
                FROM summaries
                WHERE item_id = ? AND provider = ? AND model = ?
                """,
                (item_id, provider, model),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT *
                FROM summaries
                WHERE item_id = ?
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_summary(
        self,
        item_id: str,
        provider: str,
        model: str,
        summary_md: str,
        content_hash: str | None,
    ) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO summaries(item_id, provider, model, summary_md, content_hash, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, provider, model) DO UPDATE SET
              summary_md=excluded.summary_md,
              content_hash=excluded.content_hash,
              updated_at=excluded.updated_at
            """,
            (item_id, provider, model, summary_md, content_hash, now, now),
        )
        self.conn.commit()
