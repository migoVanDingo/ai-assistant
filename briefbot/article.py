"""Article fetch/extract/cache utilities for item-level retrieval.

`get_article_for_item` fetches an item's URL, extracts readable text, stores it
under `data/article_cache`, and returns metadata suitable for context prompts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - dependency may be missing until install
    BeautifulSoup = None

from .util import ensure_dir

try:
    from readability import Document  # type: ignore

    HAS_READABILITY = True
except Exception:
    HAS_READABILITY = False


def _arxiv_abs_url(url: str) -> str:
    if "arxiv.org" not in url:
        return url
    if "/pdf/" in url:
        return url.replace("/pdf/", "/abs/").replace(".pdf", "")
    return url


def _extract_text_bs4(html: str) -> str:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required for article extraction; install requirements.txt")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "svg", "form"]):
        tag.decompose()

    article = soup.find("article")
    container = article if article else soup

    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    if not paragraphs:
        paragraphs = [container.get_text(" ", strip=True)]

    text = "\n\n".join(p for p in paragraphs if p)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _extract_arxiv(html: str) -> str:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is required for article extraction; install requirements.txt")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1", class_="title")
    abstract = soup.find("blockquote", class_="abstract")

    parts: list[str] = []
    if title:
        parts.append(title.get_text(" ", strip=True).replace("Title:", "").strip())
    if abstract:
        parts.append(abstract.get_text(" ", strip=True).replace("Abstract:", "").strip())

    if parts:
        return "\n\n".join(parts)
    return _extract_text_bs4(html)


def extract_text(html: str, url: str) -> str:
    if "arxiv.org" in url:
        return _extract_arxiv(html)

    if HAS_READABILITY:
        try:
            doc = Document(html)
            summary_html = doc.summary(html_partial=True)
            if summary_html:
                text = _extract_text_bs4(summary_html)
                if text:
                    return text
        except Exception:
            pass

    return _extract_text_bs4(html)


def _paths(cache_dir: str | Path, item_id: str) -> tuple[Path, Path, Path]:
    base = ensure_dir(cache_dir)
    text_path = base / f"{item_id}.txt"
    llm_path = base / f"{item_id}.llm.txt"
    html_path = base / f"{item_id}.html"
    return text_path, llm_path, html_path


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_article_for_item(
    item: dict[str, Any],
    cache_dir: str | Path = "data/article_cache",
    force: bool = False,
    max_bytes: int = 2_000_000,
    max_chars: int = 12_000,
    timeout: int = 20,
) -> dict[str, Any]:
    item_id = item.get("item_id")
    if not item_id:
        raise ValueError("Item has no item_id")

    text_path, llm_path, html_path = _paths(cache_dir, item_id)
    if text_path.exists() and llm_path.exists() and not force:
        text = text_path.read_text(encoding="utf-8", errors="ignore")
        llm_text = llm_path.read_text(encoding="utf-8", errors="ignore")
        return {
            "item_id": item_id,
            "path": str(text_path),
            "llm_path": str(llm_path),
            "text": text,
            "llm_text": llm_text[:max_chars],
            "content_hash": _hash_text(llm_text[:max_chars]),
            "snippet": text[:240],
            "cached": True,
        }

    url = item.get("canonical_url") or item.get("url")
    if not url:
        fallback = item.get("summary") or item.get("title") or ""
        text_path.write_text(fallback, encoding="utf-8")
        llm_path.write_text(fallback[:max_chars], encoding="utf-8")
        return {
            "item_id": item_id,
            "path": str(text_path),
            "llm_path": str(llm_path),
            "text": fallback,
            "llm_text": fallback[:max_chars],
            "content_hash": _hash_text(fallback[:max_chars]),
            "snippet": fallback[:240],
            "cached": False,
        }

    target_url = _arxiv_abs_url(url)
    resp = requests.get(
        target_url,
        timeout=timeout,
        headers={"User-Agent": "briefbot/1.0"},
        allow_redirects=True,
    )
    resp.raise_for_status()

    content = resp.content[:max_bytes]
    html = content.decode(resp.encoding or "utf-8", errors="ignore")
    html_path.write_text(html, encoding="utf-8")

    text = extract_text(html, target_url)
    if not text.strip():
        text = item.get("summary") or item.get("title") or ""

    llm_text = text[:max_chars]
    text_path.write_text(text, encoding="utf-8")
    llm_path.write_text(llm_text, encoding="utf-8")

    return {
        "item_id": item_id,
        "path": str(text_path),
        "llm_path": str(llm_path),
        "text": text,
        "llm_text": llm_text,
        "content_hash": _hash_text(llm_text),
        "snippet": text[:240],
        "cached": False,
    }
