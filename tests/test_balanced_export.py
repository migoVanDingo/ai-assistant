"""Unit tests for balanced export caps and diversification behavior."""

import unittest

from briefbot.export import _select_balanced


class TestBalancedExport(unittest.TestCase):
    def test_aggregator_caps(self) -> None:
        items = []
        for i in range(30):
            items.append(
                {
                    "item_id": f"agg-{i}",
                    "source_id": "hn_top",
                    "source_name": "HN",
                    "source_category": "aggregator",
                    "source_tier": 2,
                    "source_max_daily": 6,
                    "title": f"HN item {i} ai agents",
                    "score": 10 - (i * 0.1),
                    "tags": ["hn"],
                }
            )
        for i in range(20):
            items.append(
                {
                    "item_id": f"sec-{i}",
                    "source_id": "sec",
                    "source_name": "Security",
                    "source_category": "security",
                    "source_tier": 1,
                    "title": f"Security update CVE {i}",
                    "score": 9 - (i * 0.1),
                    "tags": ["security"],
                }
            )

        selected = _select_balanced(items, limit=50)
        agg = [i for i in selected if i.get("source_category") == "aggregator"]
        self.assertLessEqual(len(agg), 12)
        hn = [i for i in agg if i.get("source_id") == "hn_top"]
        self.assertLessEqual(len(hn), 6)


if __name__ == "__main__":
    unittest.main()
