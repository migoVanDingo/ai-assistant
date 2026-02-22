"""Configuration loader and validator for source definitions.

Key API:
- `load_config`: reads `sources.yaml`, validates required fields/types, and
  returns normalized source records consumed by `briefbot.cli`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


VALID_SOURCE_TYPES = {"rss", "site", "hn", "arxiv"}


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

        normalized.append(src)

    return {"sources": normalized}
