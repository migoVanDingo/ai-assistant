"""Unit tests for clustering behavior on a synthetic dataset."""

import tempfile
import unittest
from datetime import datetime, timezone

from briefbot.cluster import cluster_items_for_window
from briefbot.store import Store
from briefbot.util import stable_hash, utc_now_iso


class TestClustering(unittest.TestCase):
    def test_related_titles_cluster_together(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Store(f"{td}/briefbot.db")
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

            items = [
                {
                    "item_id": stable_hash("1"),
                    "dedupe_key": "url:https://example.com/a",
                    "canonical_url": "https://example.com/a",
                    "source_id": "s1",
                    "source_name": "S1",
                    "title": "OpenAI launches new agent runtime",
                    "url": "https://example.com/a",
                    "published_at": now,
                    "fetched_at": utc_now_iso(),
                    "author": "",
                    "summary": "",
                    "tags": ["ai"],
                    "raw": {},
                    "metrics": {},
                    "source_category": "ai_industry",
                    "source_tier": 1,
                    "source_max_daily": None,
                    "watch_hits": ["OpenAI"],
                    "score": 5.0,
                },
                {
                    "item_id": stable_hash("2"),
                    "dedupe_key": "url:https://example.com/b",
                    "canonical_url": "https://example.com/b",
                    "source_id": "s2",
                    "source_name": "S2",
                    "title": "New OpenAI agent runtime improves tool calling",
                    "url": "https://example.com/b",
                    "published_at": now,
                    "fetched_at": utc_now_iso(),
                    "author": "",
                    "summary": "",
                    "tags": ["ai"],
                    "raw": {},
                    "metrics": {},
                    "source_category": "ai_industry",
                    "source_tier": 1,
                    "source_max_daily": None,
                    "watch_hits": ["OpenAI"],
                    "score": 4.8,
                },
                {
                    "item_id": stable_hash("3"),
                    "dedupe_key": "url:https://example.com/c",
                    "canonical_url": "https://example.com/c",
                    "source_id": "s3",
                    "source_name": "S3",
                    "title": "Kubernetes release adds scheduler update",
                    "url": "https://example.com/c",
                    "published_at": now,
                    "fetched_at": utc_now_iso(),
                    "author": "",
                    "summary": "",
                    "tags": ["infra"],
                    "raw": {},
                    "metrics": {},
                    "source_category": "mlops_infra",
                    "source_tier": 1,
                    "source_max_daily": None,
                    "watch_hits": [],
                    "score": 3.0,
                },
            ]
            for item in items:
                store.upsert_item(item)

            date_str = datetime.now(timezone.utc).date().isoformat()
            stats = cluster_items_for_window(store=store, date_str=date_str, window_days=14)
            self.assertEqual(stats["items"], 3)
            self.assertGreaterEqual(stats["clusters"], 2)

            c1 = store.get_cluster_for_item(items[0]["item_id"])
            c2 = store.get_cluster_for_item(items[1]["item_id"])
            self.assertEqual(c1, c2)
            store.close()


if __name__ == "__main__":
    unittest.main()
