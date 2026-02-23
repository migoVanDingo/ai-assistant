"""Configuration loader and validator for source definitions.

Key API:
- `load_config`: reads `sources.yaml`, validates required fields/types, infers
  category/tier defaults, and returns normalized source records.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


VALID_SOURCE_TYPES = {"rss", "site", "hn", "arxiv"}
VALID_CATEGORIES = {
    "ai_research",
    "ai_industry",
    "devtools",
    "mlops_infra",
    "security",
    "tech_news",
    "aggregator",
    "papers",
}


def _infer_category_and_tier(src: dict[str, Any]) -> tuple[str, int]:
    tags = {str(t).lower() for t in (src.get("tags") or [])}
    source_type = src.get("type")

    if source_type == "hn":
        return "aggregator", 2
    if "papers" in tags or source_type == "arxiv":
        return "papers", 1
    if "security" in tags or "vulnerability" in tags:
        tier = 1 if source_type in {"rss", "site"} else 2
        return "security", tier
    if "devtools" in tags:
        return "devtools", 2
    if "infra" in tags or "kubernetes" in tags or "postgres" in tags or "cloud" in tags:
        return "mlops_infra", 2
    if "research" in tags:
        return "ai_research", 1
    if "ai" in tags or "industry" in tags:
        return "ai_industry", 2
    return "tech_news", 2


def load_config(path: str | Path = "sources.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources.yaml must contain a top-level 'sources' list")

    normalized = []
    ids: set[str] = set()
    for raw in sources:
        src = dict(raw or {})
        src_id = src.get("id")
        src_type = src.get("type")
        if not src_id or not isinstance(src_id, str):
            raise ValueError(f"Each source needs a string id: {raw}")
        if src_id in ids:
            raise ValueError(f"Duplicate source id: {src_id}")
        ids.add(src_id)

        if src_type not in VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source type for {src_id}: {src_type}")

        src.setdefault("name", src_id)
        src.setdefault("tags", [])
        src.setdefault("weight", 1.0)
        src.setdefault("limit", 50)
        if not isinstance(src["tags"], list):
            raise ValueError(f"Source {src_id} tags must be a list")

        # Backward compatibility for arXiv category-mode configs that used
        # `category: cs.AI` before source categorization was introduced.
        if src_type == "arxiv" and src.get("mode", "category") == "category":
            if src.get("arxiv_category") is None and src.get("category") not in VALID_CATEGORIES:
                src["arxiv_category"] = src.get("category")
                src.pop("category", None)

        inferred_category, inferred_tier = _infer_category_and_tier(src)
        src.setdefault("category", inferred_category)
        src.setdefault("tier", inferred_tier)
        src.setdefault("max_daily", None)

        if src["category"] not in VALID_CATEGORIES:
            raise ValueError(f"Source {src_id} has invalid category: {src['category']}")
        try:
            src["tier"] = int(src["tier"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Source {src_id} tier must be an integer") from exc
        if src["tier"] < 1 or src["tier"] > 3:
            raise ValueError(f"Source {src_id} tier must be between 1 and 3")

        if src.get("max_daily") is not None:
            try:
                src["max_daily"] = int(src["max_daily"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Source {src_id} max_daily must be an integer") from exc
            if src["max_daily"] <= 0:
                raise ValueError(f"Source {src_id} max_daily must be > 0")

        normalized.append(src)

    return {"sources": normalized}
