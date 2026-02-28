"""LLM-backed executive synthesis for the daily brief.

This layer sits on top of existing ranked/exported items. It fetches article
excerpts, caches stage-1 JSON summaries by stable content hash, then reduces
those JSON objects into two short narrative sections for the morning brief.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse

from .article import fetch_article_for_url
from .llm import generate_text
from .util import stable_hash

SATIRE_DOMAINS = {
    "theonion.com",
    "clickhole.com",
    "reductress.com",
    "babylonbee.com",
    "waterfordwhispersnews.com",
    "thehardtimes.net",
}

PAYWALL_MARKERS = {
    "subscribe to continue",
    "subscriber only",
    "subscription required",
    "sign in to continue",
    "start your subscription",
    "already a subscriber",
}

PARODY_MARKERS = {
    "satire",
    "parody",
    "fictional",
}


def exec_summary_enabled() -> bool:
    return os.getenv("BRIEFBOT_ENABLE_EXEC_SUMMARY", "true").strip().lower() not in {"0", "false", "no", "off"}


def default_provider() -> str:
    return os.getenv("BRIEFBOT_LLM_PROVIDER", "anthropic").strip() or "anthropic"


def default_model(model_override: str | None = None) -> str:
    if model_override:
        return model_override.strip()
    return (
        os.getenv("BRIEFBOT_MODEL_FOR_SUMMARIES")
        or os.getenv("BRIEFBOT_LLM_MODEL")
        or "claude-haiku-latest"
    ).strip()


def max_chars_per_article() -> int:
    try:
        return int(os.getenv("BRIEFBOT_MAX_CHARS_PER_ARTICLE", "12000"))
    except Exception:
        return 12000


def top_links_summary_count() -> int:
    try:
        return int(os.getenv("BRIEFBOT_N_TOP_LINKS_TO_SUMMARIZE", "10"))
    except Exception:
        return 10


def trends_summary_count() -> int:
    try:
        return int(os.getenv("BRIEFBOT_N_TRENDS_TO_SUMMARIZE", "5"))
    except Exception:
        return 5


def summary_cache_key(url: str, excerpt_text: str) -> str:
    return stable_hash(url.strip().lower(), excerpt_text.strip(), length=40)


def _excerpt_hash(excerpt_text: str) -> str:
    return stable_hash("excerpt", excerpt_text.strip(), length=40)


def _domain(url: str) -> str:
    domain = urlparse(url or "").netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _flags_for_excerpt(url: str, excerpt_text: str) -> list[str]:
    flags: list[str] = []
    domain = _domain(url)
    low = (excerpt_text or "").lower()
    if domain in SATIRE_DOMAINS:
        flags.append("satire_suspected")
    if any(marker in low for marker in PARODY_MARKERS):
        flags.append("satire_suspected")
    if any(marker in low for marker in PAYWALL_MARKERS):
        flags.append("paywalled")
    if len((excerpt_text or "").strip()) < 350:
        flags.append("excerpt_too_short")
    return sorted(set(flags))


def _confidence_from_flags(flags: list[str], excerpt_text: str) -> str:
    if "extraction_failed" in flags:
        return "low"
    if "satire_suspected" in flags or "paywalled" in flags:
        return "low"
    if "excerpt_too_short" in flags or len((excerpt_text or "").strip()) < 900:
        return "med"
    return "high"


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _coerce_stage1(data: dict[str, Any], *, title: str, url: str, flags: list[str], excerpt_text: str) -> dict[str, Any]:
    result = {
        "title": data.get("title") or title,
        "url": data.get("url") or url,
        "takeaway": str(data.get("takeaway") or "").strip(),
        "key_points": [str(x).strip() for x in (data.get("key_points") or []) if str(x).strip()],
        "entities": [str(x).strip() for x in (data.get("entities") or []) if str(x).strip()],
        "confidence": str(data.get("confidence") or _confidence_from_flags(flags, excerpt_text)).strip().lower(),
        "flags": sorted(set(flags + [str(x).strip() for x in (data.get("flags") or []) if str(x).strip()])),
    }
    if result["confidence"] not in {"high", "med", "low"}:
        result["confidence"] = _confidence_from_flags(result["flags"], excerpt_text)
    if not result["takeaway"]:
        if "extraction_failed" in result["flags"]:
            result["takeaway"] = "Extraction failed; no reliable article summary was available."
        elif excerpt_text.strip():
            result["takeaway"] = excerpt_text.strip().split(". ")[0].strip()
        else:
            result["takeaway"] = "Insufficient source text to summarize confidently."
    return result


def _stage1_prompt(title: str, url: str, excerpt_text: str, flags: list[str]) -> str:
    return (
        "You are producing a strict JSON map summary for a morning brief.\n"
        "Return JSON only. No markdown, no prose outside JSON.\n"
        "Use only facts supported by the excerpt. If unsupported, omit the claim.\n"
        "Schema:\n"
        '{\n'
        '  "title": "...",\n'
        '  "url": "...",\n'
        '  "takeaway": "one sentence",\n'
        '  "key_points": ["...","..."],\n'
        '  "entities": ["..."],\n'
        '  "confidence": "high|med|low",\n'
        '  "flags": ["paywalled|satire_suspected|excerpt_too_short|extraction_failed"]\n'
        '}\n\n'
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Precomputed flags: {', '.join(flags) if flags else '(none)'}\n\n"
        f"Excerpt:\n{excerpt_text}"
    )


def _reduce_prompt(kind: str, stage1_items: list[dict[str, Any]]) -> str:
    payload = json.dumps(stage1_items, indent=2, ensure_ascii=True)
    if kind == "top_links":
        return (
            "You are writing the opening section of a technical morning brief.\n"
            "Based only on the JSON summaries provided, write a coherent newspaper-style section titled implicitly "
            "\"What's going on\".\n"
            "Do not use bullet points. Write 2-4 short paragraphs. Group into 3-6 storylines if possible.\n"
            "End with a short sentence beginning exactly with 'What to watch next:'\n"
            "If a source appears satirical, low-signal, or unverifiable from the excerpt, say so briefly.\n"
            "Do not invent facts.\n\n"
            f"JSON summaries:\n{payload}"
        )
    return (
        "You are writing the trends section of a technical morning brief.\n"
        "Based only on the JSON summaries provided, write coherent paragraphs for \"What's trending\".\n"
        "Do not use bullet points. Write 1-3 short paragraphs.\n"
        "Call out recurring themes/clusters and why they matter.\n"
        "If confidence is low or excerpts are thin, say so briefly rather than overclaiming.\n"
        "Do not invent facts.\n\n"
        f"JSON summaries:\n{payload}"
    )


def _fetch_excerpt(url: str, max_chars: int) -> tuple[str, list[str]]:
    try:
        article = fetch_article_for_url(url=url, max_chars=max_chars)
        excerpt = article.get("llm_text") or article.get("text") or ""
        flags = _flags_for_excerpt(url, excerpt)
        return excerpt, flags
    except Exception:
        return "", ["extraction_failed"]


def build_stage1_summary(
    *,
    store,
    title: str,
    url: str,
    provider: str,
    model: str,
    max_chars: int,
) -> dict[str, Any]:
    excerpt_text, flags = _fetch_excerpt(url, max_chars=max_chars)
    cache_key = summary_cache_key(url, excerpt_text)
    cached = store.get_exec_summary_cache(cache_key)
    if cached and cached.get("stage1_json"):
        try:
            return json.loads(cached["stage1_json"])
        except Exception:
            pass

    if "extraction_failed" in flags:
        result = _coerce_stage1({}, title=title, url=url, flags=flags, excerpt_text=excerpt_text)
        store.upsert_exec_summary_cache(
            cache_key=cache_key,
            url=url,
            excerpt_hash=_excerpt_hash(excerpt_text),
            excerpt_text=excerpt_text,
            stage1_json=json.dumps(result, ensure_ascii=True),
            provider=provider,
            model=model,
        )
        return result

    prompt = _stage1_prompt(title=title, url=url, excerpt_text=excerpt_text, flags=flags)
    raw = generate_text(prompt=prompt, provider=provider, model=model, max_tokens=600, temperature=0.1)
    data = _extract_json(raw)
    result = _coerce_stage1(data, title=title, url=url, flags=flags, excerpt_text=excerpt_text)
    store.upsert_exec_summary_cache(
        cache_key=cache_key,
        url=url,
        excerpt_hash=_excerpt_hash(excerpt_text),
        excerpt_text=excerpt_text,
        stage1_json=json.dumps(result, ensure_ascii=True),
        provider=provider,
        model=model,
    )
    return result


def build_exec_summaries(
    *,
    store,
    top_link_items: list[dict[str, Any]],
    trend_clusters: list[dict[str, Any]],
    provider: str | None = None,
    model: str | None = None,
    max_chars: int | None = None,
    top_links_n: int | None = None,
    trends_n: int | None = None,
) -> dict[str, Any]:
    provider = provider or default_provider()
    model = default_model(model)
    max_chars = max_chars or max_chars_per_article()
    top_links_n = top_links_n or top_links_summary_count()
    trends_n = trends_n or trends_summary_count()

    top_stage1 = [
        build_stage1_summary(
            store=store,
            title=item.get("title") or "(untitled)",
            url=item.get("url") or "",
            provider=provider,
            model=model,
            max_chars=max_chars,
        )
        for item in top_link_items[:top_links_n]
        if item.get("url")
    ]

    trend_stage1 = [
        build_stage1_summary(
            store=store,
            title=cluster.get("representative_title") or cluster.get("label") or "(untitled)",
            url=cluster.get("representative_url") or "",
            provider=provider,
            model=model,
            max_chars=max_chars,
        )
        for cluster in trend_clusters[:trends_n]
        if cluster.get("representative_url")
    ]

    top_links_text = ""
    trends_text = ""
    if top_stage1:
        top_links_text = generate_text(
            prompt=_reduce_prompt("top_links", top_stage1),
            provider=provider,
            model=model,
            max_tokens=900,
            temperature=0.1,
        ).strip()
    if trend_stage1:
        trends_text = generate_text(
            prompt=_reduce_prompt("trends", trend_stage1),
            provider=provider,
            model=model,
            max_tokens=700,
            temperature=0.1,
        ).strip()

    return {
        "provider": provider,
        "model": model,
        "top_links_stage1": top_stage1,
        "trends_stage1": trend_stage1,
        "exec_summary_top_links": top_links_text,
        "exec_summary_trends": trends_text,
    }
