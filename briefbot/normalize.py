"""Normalization layer for converting raw source payloads into one schema.

Provides source-specific normalizers (`normalize_feed_entry`,
`normalize_hn_item`, `normalize_arxiv_entry`) that produce fields expected by
storage/scoring/export, including canonical URL and dedupe keys.
"""

from __future__ import annotations

from typing import Any

from .util import canonicalize_url, normalize_text, parse_to_utc_iso, stable_hash, utc_now_iso


def _dedupe_key(source_id: str, canonical_url: str | None, title: str, source_name: str, published_at: str | None) -> str:
    if canonical_url:
        return f"url:{canonical_url}"
    fallback = stable_hash(title.lower(), source_name.lower(), published_at or "")
    return f"fallback:{source_id}:{fallback}"


def _base_item(
    source: dict[str, Any],
    title: str,
    url: str | None,
    published_at: str | None,
    author: str | None,
    summary: str | None,
    raw: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    watch_hits: list[str] | None = None,
) -> dict[str, Any]:
    source_id = source["id"]
    source_name = source.get("name", source_id)
    canonical_url = canonicalize_url(url) if url else None
    published_iso = parse_to_utc_iso(published_at)
    fetched_at = utc_now_iso()

    dedupe_key = _dedupe_key(source_id, canonical_url, title, source_name, published_iso)
    item_id = stable_hash(source_id, canonical_url or "", dedupe_key)

    return {
        "item_id": item_id,
        "dedupe_key": dedupe_key,
        "canonical_url": canonical_url,
        "source_id": source_id,
        "source_name": source_name,
        "title": normalize_text(title) or "(untitled)",
        "url": canonical_url or url,
        "published_at": published_iso,
        "fetched_at": fetched_at,
        "author": normalize_text(author),
        "summary": normalize_text(summary),
        "tags": source.get("tags", []),
        "raw": raw,
        "metrics": metrics or {},
        "source_category": source.get("category"),
        "source_tier": source.get("tier"),
        "source_max_daily": source.get("max_daily"),
        "watch_hits": watch_hits or [],
        "score": 0.0,
    }


def normalize_feed_entry(source: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    title = entry.get("title") or ""
    url = entry.get("link")
    published = entry.get("published") or entry.get("updated")
    author = entry.get("author")
    summary = entry.get("summary") or entry.get("description")
    raw = {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "link": entry.get("link"),
        "published": entry.get("published"),
        "updated": entry.get("updated"),
        "author": entry.get("author"),
    }
    return _base_item(source, title, url, published, author, summary, raw)


def normalize_hn_item(source: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    hn_id = item.get("id")
    url = item.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
    published = item.get("time")
    if isinstance(published, (int, float)):
        from datetime import datetime, timezone

        published = datetime.fromtimestamp(published, tz=timezone.utc).isoformat()

    metrics = {
        "hn_score": item.get("score"),
        "hn_comments": item.get("descendants"),
    }
    raw = {
        "id": item.get("id"),
        "type": item.get("type"),
        "by": item.get("by"),
        "kids": item.get("kids"),
    }
    return _base_item(
        source=source,
        title=item.get("title") or "",
        url=url,
        published_at=published,
        author=item.get("by"),
        summary=item.get("text"),
        raw=raw,
        metrics=metrics,
    )


def normalize_arxiv_entry(source: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    title = entry.get("title") or ""
    link = entry.get("link")
    pdf_link = None
    for lnk in entry.get("links", []):
        href = lnk.get("href")
        if href and "pdf" in href:
            pdf_link = href
            break

    authors = entry.get("authors") or []
    author = ", ".join(a.get("name") for a in authors if a.get("name")) if authors else entry.get("author")

    raw = {
        "id": entry.get("id"),
        "arxiv_primary_category": entry.get("arxiv_primary_category"),
        "pdf_link": pdf_link,
        "tags": entry.get("tags"),
    }
    normalized = _base_item(
        source=source,
        title=title,
        url=pdf_link or link,
        published_at=entry.get("published") or entry.get("updated"),
        author=author,
        summary=entry.get("summary"),
        raw=raw,
    )
    if pdf_link:
        normalized["raw"]["pdf_link"] = pdf_link
    return normalized
