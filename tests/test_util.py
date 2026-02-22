"""Unit tests for URL canonicalization helpers in `briefbot.util`."""

import unittest

from briefbot.util import canonicalize_url


class TestCanonicalizeUrl(unittest.TestCase):
    def test_removes_tracking_and_fragment(self) -> None:
        url = "https://Example.com/path/?utm_source=x&gclid=y&id=42#section"
        self.assertEqual(canonicalize_url(url), "https://example.com/path?id=42")

    def test_strips_trailing_slash(self) -> None:
        self.assertEqual(canonicalize_url("https://example.com/path/"), "https://example.com/path")


if __name__ == "__main__":
    unittest.main()
