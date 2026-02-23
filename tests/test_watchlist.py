"""Unit tests for watchlist matching helpers."""

import unittest

from briefbot.watchlist import match_watchlist


class TestWatchlist(unittest.TestCase):
    def test_match_watchlist_hits(self) -> None:
        watchlist = {
            "people": [{"name": "Sam Altman", "aliases": ["Altman"]}],
            "orgs": [{"name": "OpenAI", "aliases": ["OpenAI"]}],
            "products": [{"name": "ElevenLabs", "aliases": ["Eleven Labs"]}],
        }
        hits = match_watchlist(
            title="Sam Altman discusses OpenAI roadmap",
            summary="Interview includes Eleven Labs integration",
            watchlist=watchlist,
        )
        self.assertIn("Sam Altman", hits)
        self.assertIn("OpenAI", hits)
        self.assertIn("ElevenLabs", hits)


if __name__ == "__main__":
    unittest.main()
