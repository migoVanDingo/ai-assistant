"""Unit tests for executive summary caching and fallback behavior."""

import json
import tempfile
import unittest
from unittest.mock import patch

from briefbot.executive import build_stage1_summary, summary_cache_key
from briefbot.store import Store


class TestExecutiveSummary(unittest.TestCase):
    def test_summary_cache_key_is_stable(self) -> None:
        url = "https://example.com/story"
        excerpt = "A stable excerpt for hashing."
        self.assertEqual(summary_cache_key(url, excerpt), summary_cache_key(url, excerpt))
        self.assertNotEqual(summary_cache_key(url, excerpt), summary_cache_key(url, excerpt + " more"))

    def test_build_stage1_summary_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Store(f"{td}/briefbot.db")
            article = {
                "llm_text": "This is a sufficiently long excerpt. " * 40,
                "text": "This is a sufficiently long excerpt. " * 40,
            }
            raw_json = json.dumps(
                {
                    "title": "Example story",
                    "url": "https://example.com/story",
                    "takeaway": "One sentence takeaway.",
                    "key_points": ["Point A", "Point B"],
                    "entities": ["ExampleCo"],
                    "confidence": "high",
                    "flags": [],
                }
            )
            with patch("briefbot.executive.fetch_article_for_url", return_value=article), patch(
                "briefbot.executive.generate_text", return_value=raw_json
            ) as generate:
                first = build_stage1_summary(
                    store=store,
                    title="Example story",
                    url="https://example.com/story",
                    provider="anthropic",
                    model="test-model",
                    max_chars=12000,
                )
                second = build_stage1_summary(
                    store=store,
                    title="Example story",
                    url="https://example.com/story",
                    provider="anthropic",
                    model="test-model",
                    max_chars=12000,
                )

            self.assertEqual(first["takeaway"], "One sentence takeaway.")
            self.assertEqual(first, second)
            self.assertEqual(generate.call_count, 1)
            store.close()

    def test_build_stage1_summary_handles_extraction_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Store(f"{td}/briefbot.db")
            url = "https://example.com/fail"
            with patch("briefbot.executive.fetch_article_for_url", side_effect=RuntimeError("boom")), patch(
                "briefbot.executive.generate_text"
            ) as generate:
                result = build_stage1_summary(
                    store=store,
                    title="Broken story",
                    url=url,
                    provider="anthropic",
                    model="test-model",
                    max_chars=12000,
                )

            self.assertIn("extraction_failed", result["flags"])
            self.assertEqual(result["confidence"], "low")
            self.assertEqual(generate.call_count, 0)
            cached = store.get_exec_summary_cache(summary_cache_key(url, ""))
            self.assertIsNotNone(cached)
            store.close()


if __name__ == "__main__":
    unittest.main()
