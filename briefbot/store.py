"""SQLite persistence for feed cache, discovery cache, and normalized items.

Core responsibilities:
- initialize schema
- cache discovery/feed headers (ETag/Last-Modified)
- upsert items with dedupe behavior
- query items for daily export
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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

CREATE INDEX IF NOT EXISTS idx_items_fetched_at ON items(fetched_at);
CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_source_id ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC);
"""


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
        self.conn.commit()

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
        import json

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
                    "UPDATE items SET last_seen_at = ?, score = ?, fetched_at = ? WHERE dedupe_key = ?",
                    (now, item["score"], item["fetched_at"], item["dedupe_key"]),
                )
                self.conn.commit()
            return UpsertResult(inserted=False, duplicate=True)

        if dry_run:
            return UpsertResult(inserted=True, duplicate=False)

        q = """
        INSERT INTO items(
            item_id, dedupe_key, canonical_url, source_id, source_name, title, url,
            published_at, fetched_at, last_seen_at, author, summary, tags_json,
            raw_json, metrics_json, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self.conn.commit()
        return UpsertResult(inserted=True, duplicate=False)

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

        import json

        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item.pop("tags_json") or "[]")
            item["raw"] = json.loads(item.pop("raw_json") or "{}")
            item["metrics"] = json.loads(item.pop("metrics_json")) if item.get("metrics_json") else {}
            out.append(item)
        return out
