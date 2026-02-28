"""Unit tests for daily brief layout and executive summary sections."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briefbot.brief import write_daily_brief


class TestDailyBrief(unittest.TestCase):
    def test_write_daily_brief_uses_executive_layout_and_limits_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            digest_dir = Path(td) / "daily_digest"
            out_dir = Path(td) / "briefs"
            digest_dir.mkdir(parents=True, exist_ok=True)

            balanced_items = [
                {
                    "item_id": f"b{i}",
                    "title": f"Top link {i}",
                    "url": f"https://example.com/top-{i}",
                    "source_name": "Example",
                    "source_category": "news",
                    "score": 10 - i,
                    "tags": ["news"],
                }
                for i in range(1, 13)
            ]
            trends = [
                {
                    "cluster_id": f"c{i}",
                    "label": f"Cluster {i}",
                    "representative_title": f"Trend story {i}",
                    "representative_url": f"https://example.com/trend-{i}",
                    "trend_score": 20 - i,
                    "velocity_7d": i,
                    "sources_count": 2,
                }
                for i in range(1, 7)
            ]
            opportunities = [
                {
                    "item_id": f"o{i}",
                    "title": f"Opportunity {i}",
                    "url": "https://github.com/example/tool" if i == 1 else f"https://example.com/opp-{i}",
                    "source_name": "Example",
                    "score": 5 - i,
                    "score_opportunity": 0.5,
                    "tags": ["automation"],
                }
                for i in range(1, 7)
            ]
            followups = [
                {
                    "cluster_id": f"f{i}",
                    "label": f"Followup {i}",
                    "new_items": [{"item_id": f"fi{i}", "title": f"Followup lead {i}", "url": f"https://example.com/follow-{i}"}],
                }
                for i in range(1, 7)
            ]

            (digest_dir / "2026-02-28.balanced.json").write_text(json.dumps({"items": balanced_items}), encoding="utf-8")
            (digest_dir / "2026-02-28.trends.json").write_text(json.dumps({"clusters": trends}), encoding="utf-8")
            (digest_dir / "2026-02-28.opportunities.json").write_text(
                json.dumps({"items": opportunities}), encoding="utf-8"
            )
            (digest_dir / "2026-02-28.followups.json").write_text(
                json.dumps({"clusters": followups}), encoding="utf-8"
            )

            with patch(
                "briefbot.executive.build_exec_summaries",
                return_value={
                    "exec_summary_top_links": "Paragraph one.\n\nWhat to watch next: Watch this.",
                    "exec_summary_trends": "Trend paragraph.",
                },
            ):
                out_path = write_daily_brief(
                    date_str="2026-02-28",
                    digest_dir=digest_dir,
                    out_dir=out_dir,
                    db_path=Path(td) / "briefbot.db",
                    enable_exec_summary=True,
                    exec_summary_model="test-model",
                )

            text = out_path.read_text(encoding="utf-8")
            self.assertIn("## What’s going on", text)
            self.assertIn("## What’s trending", text)
            self.assertIn("## Top Links", text)
            self.assertNotIn("## Topics", text)
            self.assertIn("10. [Top link 10]", text)
            self.assertNotIn("11. [Top link 11]", text)
            self.assertIn("5. [Trend story 5]", text)
            self.assertNotIn("6. [Trend story 6]", text)
            self.assertIn("5. [Opportunity 5]", text)
            self.assertNotIn("6. [Opportunity 6]", text)
            self.assertIn("5. **Followup 5**", text)
            self.assertNotIn("6. **Followup 6**", text)
            self.assertIn("## Today’s Moves", text)


if __name__ == "__main__":
    unittest.main()
