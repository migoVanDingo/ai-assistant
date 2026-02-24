"""Deterministic topic profile extraction and momentum computation."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser as dtparser

from .util import stable_hash

ENTITY_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "with",
    "new",
    "show",
    "how",
    "why",
    "what",
    "when",
    "where",
    "in",
    "on",
    "to",
    "from",
    "of",
}

ENTITY_SUFFIXES = {"inc", "ai", "labs", "corp", "llc", "ltd", "systems", "technologies"}

TOPIC_STOPWORDS = {
    "after",
    "before",
    "during",
    "while",
    "who",
    "whom",
    "whose",
    "what",
    "which",
    "when",
    "where",
    "but",
    "not",
    "one",
    "time",
    "first",
    "long",
    "fine",
    "years",
    "year",
    "day",
    "days",
    "self",
    "over",
    "under",
    "up",
    "down",
    "out",
    "more",
    "most",
    "less",
    "least",
}


def _to_dt(value: str | None) -> datetime:
    if not value:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        dt = dtparser.parse(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def extract_entities_from_title(title: str) -> list[str]:
    if not title:
        return []

    entities: list[str] = []
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\.]+", title)

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        tok_clean = tok.strip(". ")
        low = tok_clean.lower()

        is_capitalized = tok_clean[:1].isupper() or tok_clean.isupper()
        is_suffix = low in ENTITY_SUFFIXES
        if not (is_capitalized or is_suffix):
            i += 1
            continue
        if low in ENTITY_STOPWORDS:
            i += 1
            continue

        phrase_parts = [tok_clean]
        j = i + 1
        while j < len(tokens):
            nxt = tokens[j].strip(". ")
            nxt_low = nxt.lower()
            if nxt_low in ENTITY_STOPWORDS:
                break
            if nxt[:1].isupper() or nxt.isupper() or nxt_low in ENTITY_SUFFIXES:
                phrase_parts.append(nxt)
                j += 1
                continue
            break

        phrase = " ".join(phrase_parts).strip()
        if len(phrase) >= 3 and phrase.lower() not in ENTITY_STOPWORDS:
            entities.append(phrase)
        i = j

    # de-duplicate preserving order
    out: list[str] = []
    seen: set[str] = set()
    for ent in entities:
        key = ent.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ent)
    return out


def _good_topic_token(t: str) -> bool:
    tok = (t or "").strip().lower()
    if len(tok) < 4:
        return False
    if tok in TOPIC_STOPWORDS:
        return False
    if tok.isnumeric():
        return False
    if not any(ch.isalpha() for ch in tok):
        return False
    return True


def compute_topic_profiles(store, date_str: str, window_days: int = 30) -> dict[str, int]:
    items = store.fetch_items_in_window(date_str, window_days=window_days)
    if not items:
        return {"items": 0, "topics": 0}

    # Recompute topic profiles deterministically for the current run/window.
    try:
        store.conn.execute("DELETE FROM topic_profiles")
        store.conn.commit()
    except Exception:
        pass

    ref_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = ref_dt - timedelta(days=1)
    d3 = ref_dt - timedelta(days=3)
    d7 = ref_dt - timedelta(days=7)
    d30 = ref_dt - timedelta(days=30)

    topic_data: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "first_seen_at": None,
            "last_seen_at": None,
            "count_1d": 0,
            "count_3d": 0,
            "count_7d": 0,
            "count_30d": 0,
        }
    )

    for item in items:
        item_dt = _to_dt(item.get("published_at") or item.get("fetched_at"))
        if item_dt < d30:
            continue

        topics: list[tuple[str, str]] = []

        for ent in extract_entities_from_title(item.get("title") or ""):
            topics.append(("entity", ent))

        for tag in item.get("tags") or []:
            t = str(tag).strip().lower()
            if t:
                topics.append(("token", t))

        cluster_id = store.get_cluster_for_item(item.get("item_id") or "")
        if cluster_id:
            cluster = store.get_cluster(cluster_id)
            if cluster:
                for tok in (cluster.get("top_tokens") or [])[:1]:
                    t = str(tok).strip().lower()
                    if _good_topic_token(t):
                        topics.append(("token", t))

        # per-item unique topics
        seen_local: set[tuple[str, str]] = set()
        for kind, name in topics:
            key = (kind, name)
            if key in seen_local:
                continue
            seen_local.add(key)

            rec = topic_data[key]
            first = rec["first_seen_at"]
            last = rec["last_seen_at"]
            rec["first_seen_at"] = item_dt if first is None or item_dt < first else first
            rec["last_seen_at"] = item_dt if last is None or item_dt > last else last
            rec["count_30d"] += 1
            if item_dt >= d7:
                rec["count_7d"] += 1
            if item_dt >= d3:
                rec["count_3d"] += 1
            if item_dt >= d1:
                rec["count_1d"] += 1

    upserted = 0
    for (kind, name), rec in topic_data.items():
        c1 = rec["count_1d"]
        c3 = rec["count_3d"]
        c7 = rec["count_7d"]
        c30 = rec["count_30d"]
        momentum = round((c3 - (c7 / 2.0)) + (0.4 * c1) + (0.05 * c30), 4)

        store.upsert_topic_profile(
            {
                "topic_id": stable_hash(kind, name.lower(), length=24),
                "name": name,
                "kind": kind,
                "first_seen_at": rec["first_seen_at"].replace(microsecond=0).isoformat() if rec["first_seen_at"] else None,
                "last_seen_at": rec["last_seen_at"].replace(microsecond=0).isoformat() if rec["last_seen_at"] else None,
                "count_1d": c1,
                "count_3d": c3,
                "count_7d": c7,
                "count_30d": c30,
                "momentum": momentum,
            }
        )
        upserted += 1

    return {"items": len(items), "topics": upserted}
