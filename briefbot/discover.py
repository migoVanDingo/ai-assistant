"""Feed discovery helpers for `type: site` sources.

Functions here fetch a webpage and parse `<link rel="alternate">` tags to
discover RSS/Atom feed URLs. `briefbot.cli` uses this during collection and
`briefbot.store` caches results to avoid rediscovery on every run.
"""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

FEED_MIME_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/rdf+xml",
    "application/xml",
    "text/xml",
}


def discover_feeds_from_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    feeds: list[str] = []
    for link in soup.find_all("link"):
        rel = {r.lower() for r in (link.get("rel") or [])}
        if "alternate" not in rel:
            continue
        href = link.get("href")
        mime_type = (link.get("type") or "").split(";")[0].strip().lower()
        if not href:
            continue
        if mime_type and mime_type not in FEED_MIME_TYPES:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in feeds:
            feeds.append(absolute)
    return feeds


def discover_site_feeds(
    site_url: str,
    timeout: int = 20,
    session: requests.Session | None = None,
    verify_ssl: bool = True,
) -> list[str]:
    sess = session or requests.Session()
    backoff = 1.0
    resp = None
    for _ in range(3):
        resp = sess.get(
            site_url,
            timeout=timeout,
            headers={"User-Agent": "briefbot/1.0"},
            verify=verify_ssl,
        )
        if resp.status_code != 429:
            break
        retry_after = resp.headers.get("Retry-After")
        sleep_s = float(retry_after) if retry_after and retry_after.isdigit() else backoff
        import time

        time.sleep(min(15.0, max(0.5, sleep_s)))
        backoff *= 2
    if resp is None:
        raise RuntimeError("No response while discovering feeds")
    resp.raise_for_status()
    return discover_feeds_from_html(resp.text, site_url)
