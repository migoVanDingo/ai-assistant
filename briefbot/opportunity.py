"""Deterministic opportunity lens scoring for briefbot items.

This module adds a second ranking lens focused on practical build/business
opportunities without modifying the primary information score.
"""

from __future__ import annotations

from typing import Any


ENABLING_TECH_KEYWORDS = {
    "ai",
    "llm",
    "agent",
    "agents",
    "agentic",
    "assistant",
    "tool",
    "tools",
    "platform",
    "plugin",
    "workflow",
    "automation",
    "automate",
    "mcp",
    "tool calling",
    "llmops",
    "model serving",
    "orchestration",
    "copilot",
    "api",
    "sdk",
    "integration",
    "zapier",
    "n8n",
    "rag",
}

PAIN_KEYWORDS = {
    "scheduling",
    "billing",
    "intake",
    "compliance",
    "paperwork",
    "reconciliation",
    "manual",
    "backlog",
    "onboarding",
    "ticket triage",
    "reporting",
    "invoice",
    "claims",
    "prior authorization",
    "ops",
    "operations",
    "workflow bottleneck",
}

REGULATORY_KEYWORDS = {
    "hipaa",
    "sox",
    "gdpr",
    "pci",
    "audit",
    "sec",
    "finra",
    "soc 2",
    "iso 27001",
    "compliance",
    "regulatory",
    "policy",
}

B2B_FIT_KEYWORDS = {
    "dentist",
    "dental",
    "clinic",
    "medical practice",
    "law firm",
    "realtor",
    "real estate",
    "accounting",
    "bookkeeping",
    "hvac",
    "plumbing",
    "contractor",
    "agency",
    "professional services",
    "smb",
    "small business",
}

NARROW_PROCESS_KEYWORDS = {
    "form",
    "document",
    "invoice",
    "intake",
    "scheduling",
    "approval",
    "triage",
    "reconcile",
    "ticket",
    "crm",
    "erp",
    "back office",
    "back-office",
}

LAUNCH_WORDS = {
    "launch",
    "launched",
    "released",
    "release",
    "beta",
    "open-sourced",
    "open source",
    "announced",
    "new tool",
    "new product",
    "show hn",
}


def _text_blob(item: dict[str, Any]) -> str:
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    tags = " ".join(str(t) for t in (item.get("tags") or []))
    return f"{title} {summary} {tags}".lower()


def _keyword_signal(text: str, keywords: set[str], saturate: int = 3) -> float:
    hits = sum(1 for kw in keywords if kw in text)
    if hits <= 0:
        return 0.0
    return min(1.0, hits / float(max(1, saturate)))


def _emergence_signal(item: dict[str, Any], text: str) -> float:
    signal = 0.0
    if any(w in text for w in LAUNCH_WORDS):
        signal += 0.4

    metrics = item.get("metrics") or {}
    hn_score = float(metrics.get("hn_score") or 0.0)
    hn_comments = float(metrics.get("hn_comments") or 0.0)
    if hn_score >= 80:
        signal += 0.25
    elif hn_score >= 30:
        signal += 0.15
    if hn_comments >= 40:
        signal += 0.2
    elif hn_comments >= 15:
        signal += 0.1

    watch_hits = item.get("watch_hits") or []
    if watch_hits:
        signal += 0.2

    # recency proxy from existing score features (without re-parsing dates)
    if float(item.get("score") or 0.0) >= 6.0:
        signal += 0.1

    return min(1.0, signal)


def _feasibility_signal(
    item: dict[str, Any],
    text: str,
    enabling_tech: float,
    pain: float,
    b2b_fit: float,
) -> float:
    feasibility = 0.25
    if _keyword_signal(text, NARROW_PROCESS_KEYWORDS, saturate=2) > 0:
        feasibility += 0.35
    if pain >= 0.34:
        feasibility += 0.2
    if b2b_fit >= 0.34:
        feasibility += 0.15

    category = (item.get("source_category") or "").lower()
    if category == "papers" and enabling_tech < 0.34:
        feasibility -= 0.35
    elif category == "papers" and enabling_tech >= 0.34:
        feasibility += 0.1

    return max(0.0, min(1.0, feasibility))


def _build_reason(components: dict[str, float], tags: list[str], text: str) -> str:
    labels = {
        "enabling_tech": "enabling-tech",
        "pain": "pain",
        "regulatory": "regulatory",
        "b2b_fit": "SMB/B2B fit",
        "feasibility": "build feasibility",
        "emergence": "emergence",
    }
    top = sorted(components.items(), key=lambda kv: kv[1], reverse=True)[:2]
    parts = [f"high {labels.get(k, k)} signal" for k, v in top if v > 0.0]
    if not parts:
        return "Limited clear opportunity signals in current metadata."

    angle = ""
    if "micro_saas" in tags and "automation" in tags:
        angle = " Likely automation/micro-SaaS angle."
    elif "service" in tags:
        angle = " Service-business workflow angle looks plausible."
    elif "content" in tags:
        angle = " Potential content/distribution opportunity."

    return " + ".join(parts).capitalize() + "." + angle


def compute_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    text = _text_blob(item)

    enabling_tech = _keyword_signal(text, ENABLING_TECH_KEYWORDS, saturate=3)
    pain = _keyword_signal(text, PAIN_KEYWORDS, saturate=3)
    regulatory = _keyword_signal(text, REGULATORY_KEYWORDS, saturate=2)
    b2b_fit = _keyword_signal(text, B2B_FIT_KEYWORDS, saturate=2)
    feasibility = _feasibility_signal(item, text, enabling_tech, pain, b2b_fit)
    emergence = _emergence_signal(item, text)

    score = (
        0.25 * enabling_tech
        + 0.30 * pain
        + 0.15 * regulatory
        + 0.15 * b2b_fit
        + 0.10 * feasibility
        + 0.05 * emergence
    )
    score = round(max(0.0, min(1.0, score)), 4)

    tags: list[str] = []
    if pain >= 0.34 and b2b_fit >= 0.34:
        tags.append("service")
    if enabling_tech >= 0.25:
        tags.append("automation")
    if regulatory >= 0.34:
        tags.append("compliance")
    if enabling_tech >= 0.34 and feasibility >= 0.45:
        tags.append("micro_saas")

    metrics = item.get("metrics") or {}
    hn_score = float(metrics.get("hn_score") or 0.0)
    hn_comments = float(metrics.get("hn_comments") or 0.0)
    if any(w in text for w in LAUNCH_WORDS) or hn_score >= 60 or hn_comments >= 25:
        tags.append("content")

    # Deterministic de-dupe while preserving insertion order.
    seen: set[str] = set()
    compact_tags: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            compact_tags.append(t)

    if score >= 0.12 and not compact_tags:
        # Ensure minimally useful labeling for non-trivial opportunities.
        if enabling_tech >= max(pain, b2b_fit, regulatory):
            compact_tags.append("automation")
        elif any(w in text for w in LAUNCH_WORDS) or hn_score >= 40:
            compact_tags.append("content")
        else:
            compact_tags.append("service")

    components = {
        "enabling_tech": round(enabling_tech, 4),
        "pain": round(pain, 4),
        "regulatory": round(regulatory, 4),
        "b2b_fit": round(b2b_fit, 4),
        "feasibility": round(feasibility, 4),
        "emergence": round(emergence, 4),
    }

    reason = _build_reason(components, compact_tags, text)

    return {
        "score_opportunity": score,
        "opportunity_reason": reason,
        "opportunity_tags": compact_tags,
        "components": components,
    }
