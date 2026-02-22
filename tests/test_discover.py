"""Unit tests for HTML feed discovery parsing in `briefbot.discover`."""

import unittest

from briefbot.discover import discover_feeds_from_html


class TestDiscoverFeeds(unittest.TestCase):
    def test_discover_feeds_from_html(self) -> None:
        html = """
        <html>
          <head>
            <link rel=\"alternate\" type=\"application/rss+xml\" href=\"/feed.xml\" />
            <link rel=\"alternate\" type=\"application/atom+xml\" href=\"https://example.com/atom.xml\" />
          </head>
        </html>
        """
        feeds = discover_feeds_from_html(html, "https://example.com/blog")
        self.assertIn("https://example.com/feed.xml", feeds)
        self.assertIn("https://example.com/atom.xml", feeds)


if __name__ == "__main__":
    unittest.main()
