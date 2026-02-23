"""Tests for rank resolver, query ranking, and citation formatting."""

import json
import tempfile
import unittest
from pathlib import Path

from briefbot.resolve import format_citation, rank_items_for_query, resolve_item_reference


class _DummyStore:
    def __init__(self, items):
        self._items = items

    def get_items_for_date(self, date_str: str, limit: int = 50):
        return self._items[:limit]


class TestResolve(unittest.TestCase):
    def test_rank_reference_prefers_export_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "2026-02-22.balanced.json"
            out.write_text(json.dumps({"items": [{"item_id": "a1"}, {"item_id": "a2"}]}), encoding="utf-8")
            store = _DummyStore(items=[{"item_id": "db1"}, {"item_id": "db2"}])
            resolved = resolve_item_reference(store, "rank:2", "2026-02-22", digest_dir=td)
            self.assertEqual(resolved, "a2")

    def test_rank_reference_falls_back_to_db(self) -> None:
        store = _DummyStore(items=[{"item_id": "db1"}, {"item_id": "db2"}, {"item_id": "db3"}])
        resolved = resolve_item_reference(store, "rank:3", "2026-02-22", digest_dir="/tmp/not-real")
        self.assertEqual(resolved, "db3")

    def test_query_ranking(self) -> None:
        items = [
            {"item_id": "1", "title": "Agentic eval pipeline", "summary": "", "source_name": "A", "tags": ["ai"], "score": 1},
            {"item_id": "2", "title": "Sports update", "summary": "", "source_name": "B", "tags": ["news"], "score": 10},
        ]
        ranked = rank_items_for_query("agentic eval", items)
        self.assertEqual(ranked[0]["item_id"], "1")

    def test_citation_markdown(self) -> None:
        item = {
            "item_id": "x1",
            "title": "Test title",
            "source_name": "Source",
            "source_id": "src",
            "published_at": "2026-02-22T00:00:00+00:00",
            "url": "https://example.com",
            "tags": ["ai"],
        }
        md = format_citation(item, fmt="md")
        self.assertIn("**Title:** Test title", md)
        self.assertIn("`x1`", md)


if __name__ == "__main__":
    unittest.main()
