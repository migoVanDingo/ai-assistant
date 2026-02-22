"""Source fetchers for RSS/Atom, Hacker News, and arXiv.

Main functions:
- `fetch_rss_feed`: HTTP fetch with cache headers + feed parsing.
- `fetch_hn_source`: pulls HN story IDs/details from Firebase API.
- `fetch_arxiv_source`: ingests arXiv category/query feeds with fallbacks.

This module returns normalized item dicts via `briefbot.normalize` and raises
`FetchError` for source-level handling in `briefbot.cli`.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests

from .normalize import normalize_arxiv_entry, normalize_feed_entry, normalize_hn_item

HN_ENDPOINTS = {
    "top": "https://hacker-news.firebaseio.com/v0/topstories.json",
    "new": "https://hacker-news.firebaseio.com/v0/newstories.json",
    "best": "https://hacker-news.firebaseio.com/v0/beststories.json",
}


class FetchError(Exception):
    def __init__(self, message: str, status_code: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


def source_homepage(source: dict[str, Any], fallback_url: str | None = None) -> str | None:
    if source.get("homepage_url"):
        return source["homepage_url"]
    raw = fallback_url or source.get("url")
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


def _request_with_retries(
    session: requests.Session,
    url: str,
    timeout: int,
    headers: dict[str, str],
    verify_ssl: bool = True,
    max_attempts: int = 3,
) -> requests.Response:
    backoff = 1.0
    last_resp: requests.Response | None = None
    for attempt in range(1, max_attempts + 1):
        resp = session.get(url, timeout=timeout, headers=headers, verify=verify_ssl)
        last_resp = resp
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After")
        sleep_s = float(retry_after) if retry_after and retry_after.isdigit() else backoff
        time.sleep(min(15.0, max(0.5, sleep_s)))
        backoff *= 2
        if attempt == max_attempts:
            return resp
    if last_resp is None:
        raise RuntimeError("No HTTP response returned")
    return last_resp


def fetch_rss_feed(
    source: dict[str, Any],
    feed_url: str,
    store,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> tuple[list[dict[str, Any]], str]:
    sess = session or requests.Session()
    headers = {"User-Agent": "briefbot/1.0"}
    headers.update(store.get_feed_cache_headers(feed_url))
    verify_ssl = bool(source.get("verify_ssl", True))

    try:
        resp = _request_with_retries(
            session=sess,
            url=feed_url,
            timeout=timeout,
            headers=headers,
            verify_ssl=verify_ssl,
        )
    except requests.exceptions.SSLError as exc:
        raise FetchError(f"Feed SSL error: {feed_url} ({exc})", url=feed_url) from exc
    except requests.RequestException as exc:
        raise FetchError(f"Feed request error: {feed_url} ({exc})", url=feed_url) from exc

    if resp.status_code == 304:
        return [], "not_modified"
    if resp.status_code >= 400:
        raise FetchError(f"Feed HTTP {resp.status_code}: {feed_url}", status_code=resp.status_code, url=feed_url)

    parsed = feedparser.parse(resp.content)
    etag = resp.headers.get("ETag") or parsed.get("etag")
    modified = resp.headers.get("Last-Modified") or parsed.get("modified")
    store.set_feed_cache_headers(feed_url, etag, modified)

    items = [normalize_feed_entry(source, dict(entry)) for entry in parsed.entries]
    return items, "ok"


def fetch_hn_source(
    source: dict[str, Any], session: requests.Session | None = None, timeout: int = 20
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    mode = source.get("mode", "top")
    if mode not in HN_ENDPOINTS:
        raise FetchError(f"Invalid HN mode '{mode}' for source {source['id']}")

    verify_ssl = bool(source.get("verify_ssl", True))
    list_url = HN_ENDPOINTS[mode]
    ids_resp = _request_with_retries(
        session=sess,
        url=list_url,
        timeout=timeout,
        headers={"User-Agent": "briefbot/1.0"},
        verify_ssl=verify_ssl,
    )
    ids_resp.raise_for_status()
    ids = ids_resp.json()[: int(source.get("limit", 30))]

    keyword = (source.get("keyword") or "").lower().strip()
    items: list[dict[str, Any]] = []
    for idx, item_id in enumerate(ids, start=1):
        detail_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
        item_resp = _request_with_retries(
            session=sess,
            url=detail_url,
            timeout=timeout,
            headers={"User-Agent": "briefbot/1.0"},
            verify_ssl=verify_ssl,
        )
        if item_resp.status_code != 200:
            continue
        data = item_resp.json() or {}
        if data.get("type") != "story":
            continue
        if keyword and keyword not in (data.get("title") or "").lower():
            continue
        items.append(normalize_hn_item(source, data))
        if idx % 8 == 0:
            time.sleep(0.15)

    return items


def _arxiv_category_url(category: str) -> str:
    return f"https://export.arxiv.org/rss/{category}"


def _arxiv_query_api(query: str, limit: int) -> str:
    from urllib.parse import quote_plus

    q = quote_plus(query)
    return f"https://export.arxiv.org/api/query?search_query={q}&start=0&max_results={limit}"


def fetch_arxiv_source(
    source: dict[str, Any], session: requests.Session | None = None, timeout: int = 20
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    mode = source.get("mode", "category")
    limit = int(source.get("limit", 50))

    if mode == "category":
        category = source.get("category")
        if not category:
            raise FetchError(f"arXiv category mode requires 'category' for {source['id']}")
        url = _arxiv_category_url(category)
        fallback_query = f"cat:{category}"
    elif mode == "query":
        query = source.get("query")
        if not query:
            raise FetchError(f"arXiv query mode requires 'query' for {source['id']}")
        url = _arxiv_query_api(query, limit)
    else:
        raise FetchError(f"Invalid arXiv mode '{mode}' for source {source['id']}")

    resp = _request_with_retries(
        session=sess,
        url=url,
        timeout=timeout,
        headers={"User-Agent": "briefbot/1.0"},
        verify_ssl=bool(source.get("verify_ssl", True)),
    )
    resp.raise_for_status()

    parsed = feedparser.parse(resp.content)
    entries = parsed.entries[:limit]

    # arXiv category RSS can intermittently return empty payloads; fallback to API query.
    if mode == "category" and len(entries) == 0:
        fallback_url = _arxiv_query_api(fallback_query, limit)
        fallback_resp = _request_with_retries(
            session=sess,
            url=fallback_url,
            timeout=timeout,
            headers={"User-Agent": "briefbot/1.0"},
            verify_ssl=bool(source.get("verify_ssl", True)),
        )
        fallback_resp.raise_for_status()
        fallback_parsed = feedparser.parse(fallback_resp.content)
        entries = fallback_parsed.entries[:limit]

    return [normalize_arxiv_entry(source, dict(entry)) for entry in entries]
