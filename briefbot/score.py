"""Rule-based item scoring (no ML/LLM).

`compute_score` combines recency, source weight, title keyword matches,
mission/watchlist signals, tier/category penalties, and HN engagement metrics
into a sortable float score.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as dtparser

KEYWORDS = {
    "agent",
    "agents",
    "rag",
    "multimodal",
    "diffusion",
    "vulnerability",
    "exploit",
    "cve",
    "sandbox",
    "wasm",
    "postgres",
    "kubernetes",
    "llm",
    "inference",
    "benchmark",
    "safety",
    "red team",
    "prompt injection",
    "supply chain",
}

MISSION_KEYWORDS = {
    "ai",
    "agent",
    "agents",
    "agentic",
    "llm",
    "mcp",
    "rag",
    "eval",
    "inference",
    "training",
    "diffusion",
    "multimodal",
    "benchmark",
    "security",
    "vulnerability",
    "cve",
    "exploit",
    "sandbox",
    "malware",
    "phishing",
    "kubernetes",
    "postgres",
    "mlops",
    "observability",
    "devtools",
    "release",
    "launch",
    "startup",
    "funding",
    "open-source",
    "github",
}


def title_matches_keywords(title: str, keywords: set[str]) -> bool:
    low = (title or "").lower()
    return any(k in low for k in keywords)


def _age_hours(iso_ts: str | None) -> float:
    if not iso_ts:
        return 9999.0
    try:
        dt = dtparser.parse(iso_ts)
    except (TypeError, ValueError, OverflowError):
        return 9999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def compute_score(item: dict[str, Any], source_weight: float = 1.0) -> float:
    title = (item.get("title") or "").lower()

    age = _age_hours(item.get("published_at") or item.get("fetched_at"))
    recency = 0.0
    if age <= 72:
        recency = (72 - age) / 72 * 2.0

    keyword_hits = sum(1 for k in KEYWORDS if k in title)
    keyword_boost = min(2.5, keyword_hits * 0.75)

    metrics = item.get("metrics") or {}
    hn_score = float(metrics.get("hn_score") or 0.0)
    hn_comments = float(metrics.get("hn_comments") or 0.0)
    hn_boost = 0.0
    if hn_score > 0:
        hn_boost += math.log1p(hn_score) * 0.4
    if hn_comments > 0:
        hn_boost += math.log1p(hn_comments) * 0.25

    watch_hits = item.get("watch_hits") or []
    watch_boost = 1.5 if watch_hits else 0.0

    category = (item.get("source_category") or "").lower()
    tier = int(item.get("source_tier") or 2)
    mission_match = title_matches_keywords(title, MISSION_KEYWORDS)

    aggregator_penalty = 0.0
    if category == "aggregator" and not mission_match:
        aggregator_penalty = 1.2

    tier_penalty = 0.0
    if tier >= 3 and not (mission_match or watch_hits):
        tier_penalty = 1.0

    base = 1.0
    score = (base + recency + keyword_boost + hn_boost + watch_boost) * max(0.1, float(source_weight or 1.0))
    score -= aggregator_penalty + tier_penalty
    return round(max(0.0, score), 4)
