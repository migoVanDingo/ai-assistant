"""Watchlist loading and deterministic entity matching utilities.

This module reads `watchlist.yaml` and matches entities against item title and
summary using case-insensitive substring checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_watchlist(path: str | Path = "watchlist.yaml") -> dict[str, list[dict[str, Any]]]:
    p = Path(path)
    if not p.exists():
        return {"people": [], "orgs": [], "products": []}

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = {
        "people": list(data.get("people") or []),
        "orgs": list(data.get("orgs") or []),
        "products": list(data.get("products") or []),
    }
    return out


def match_watchlist(
    title: str | None,
    summary: str | None,
    watchlist: dict[str, list[dict[str, Any]]],
) -> list[str]:
    haystack = f"{title or ''}\n{summary or ''}".lower()
    if not haystack.strip():
        return []

    hits: list[str] = []
    for section in ("people", "orgs", "products"):
        for entity in watchlist.get(section, []):
            name = str(entity.get("name") or "").strip()
            aliases = [name] + [str(a).strip() for a in (entity.get("aliases") or [])]
            aliases = [a for a in aliases if a]
            if not aliases:
                continue
            if any(alias.lower() in haystack for alias in aliases):
                if name and name not in hits:
                    hits.append(name)
    return hits
