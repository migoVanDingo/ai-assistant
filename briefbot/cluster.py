"""Deterministic clustering and trend computation for radar views.

`cluster_items_for_window` groups items into storylines using token similarity,
stores memberships/clusters, and computes velocity/diversity/trend metrics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from dateutil import parser as dtparser

from .store import Store
from .util import stable_hash, utc_now_iso

try:
    from rapidfuzz.fuzz import token_set_ratio  # type: ignore

    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False


STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "for",
    "in",
    "on",
    "of",
    "with",
    "at",
    "is",
    "are",
    "new",
    "how",
    "why",
    "from",
    "into",
    "by",
    "about",
    "as",
    "it",
    "its",
    "via",
    "you",
    "your",
    "this",
    "that",
    "their",
    "will",
    "can",
    "using",
    "use",
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
    "first",
    "self",
    "time",
    "year",
    "years",
    "day",
    "days",
    "long",
    "fine",
}


@dataclass
class ClusterState:
    cluster_id: str
    created_at: str
    item_ids: list[str] = field(default_factory=list)
    source_ids: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    token_counts: Counter[str] = field(default_factory=Counter)
    centroid_tokens: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)


def _to_dt(value: str | None) -> datetime:
    if value:
        try:
            dt = dtparser.parse(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _tokenize(text: str) -> set[str]:
    clean = []
    for ch in (text or "").lower():
        if ch.isalnum() or ch in {"-", "_", " ", "."}:
            clean.append(ch)
        else:
            clean.append(" ")
    tokens = []
    for t in "".join(clean).replace("_", " ").replace("-", " ").split():
        if len(t) <= 2:
            continue
        if t in STOPWORDS:
            continue
        tokens.append(t)
    return set(tokens)


def _signature(item: dict[str, Any]) -> set[str]:
    toks = set(_tokenize(item.get("title") or ""))
    domain = urlparse(item.get("url") or "").netloc.lower().replace("www.", "")
    if domain:
        toks.add(f"domain:{domain}")
    cat = (item.get("source_category") or "").lower()
    if cat:
        toks.add(f"cat:{cat}")
    for tag in item.get("tags", []) or []:
        t = str(tag).lower().strip()
        if t:
            toks.add(f"tag:{t}")
    return toks


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _similarity(item: dict[str, Any], cluster: ClusterState, sig: set[str]) -> float:
    if HAS_RAPIDFUZZ and cluster.titles:
        best = 0.0
        title = item.get("title") or ""
        for candidate in cluster.titles[-6:]:
            score = token_set_ratio(title, candidate) / 100.0
            if score > best:
                best = score
        return best
    return _jaccard(sig, cluster.centroid_tokens)


def _threshold() -> float:
    return 0.72 if HAS_RAPIDFUZZ else 0.35


def _cluster_label(cluster: ClusterState, member_items: list[dict[str, Any]]) -> str:
    watch_counter: Counter[str] = Counter()
    for item in member_items:
        for hit in item.get("watch_hits") or []:
            watch_counter[hit] += 1
    if watch_counter and member_items:
        top_hit, top_count = watch_counter.most_common(1)[0]
        dominance = top_count / max(1, len(member_items))
        if top_count >= 2 and dominance >= 0.60:
            return top_hit

    top = [tok for tok, _ in cluster.token_counts.most_common(3) if not tok.startswith(("domain:", "cat:", "tag:"))]
    if top:
        return " ".join(top)
    return "general update"


def _trend_score(v1: int, v3: int, v7: int, sources_count: int, category_count: int, watch_hits_count: int) -> float:
    base = (v1 * 3 + v3 * 2 + v7)
    multiplier = (1 + 0.35 * max(0, sources_count - 1)) * (1 + 0.25 * max(0, category_count))
    return round(base * multiplier + (2.0 * watch_hits_count), 4)


def cluster_items_for_window(
    store: Store,
    date_str: str,
    window_days: int = 14,
) -> dict[str, int]:
    items = store.fetch_items_in_window(date_str, window_days=window_days)
    if not items:
        return {"items": 0, "clusters": 0}

    store.clear_memberships_in_window(date_str=date_str, window_days=window_days)

    clusters: dict[str, ClusterState] = {}
    inverted: dict[str, set[str]] = defaultdict(set)

    for item in items:
        sig = _signature(item)
        title_toks = _tokenize(item.get("title") or "")
        candidate_ids: set[str] = set()
        for tok in list(title_toks)[:8]:
            candidate_ids |= inverted.get(tok, set())

        if not candidate_ids:
            candidate_ids = set(clusters.keys())

        best_cluster_id: str | None = None
        best_score = -1.0
        for cid in candidate_ids:
            c = clusters[cid]
            sim = _similarity(item, c, sig)
            if sim > best_score:
                best_score = sim
                best_cluster_id = cid

        if best_cluster_id is None or best_score < _threshold():
            cid = stable_hash("cluster", item["item_id"], length=24)
            cstate = ClusterState(cluster_id=cid, created_at=utc_now_iso())
            clusters[cid] = cstate
            best_cluster_id = cid
            best_score = 1.0

        cluster = clusters[best_cluster_id]
        cluster.item_ids.append(item["item_id"])
        cluster.source_ids.add(item.get("source_id") or "")
        if item.get("source_category"):
            cluster.categories.add(item["source_category"])
        cluster.token_counts.update(title_toks)
        cluster.centroid_tokens |= sig
        cluster.titles.append(item.get("title") or "")

        for tok in list(title_toks)[:8]:
            inverted[tok].add(best_cluster_id)

        store.upsert_membership(item_id=item["item_id"], cluster_id=best_cluster_id, similarity=best_score)

    ref_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = ref_dt - timedelta(days=1)
    d3 = ref_dt - timedelta(days=3)
    d7 = ref_dt - timedelta(days=7)

    for cid, state in clusters.items():
        members = [store.get_item_by_id(iid) for iid in state.item_ids]
        members = [m for m in members if m]
        if not members:
            continue

        times = [_to_dt(m.get("published_at") or m.get("fetched_at")) for m in members]
        first_seen = min(times).replace(microsecond=0).isoformat()
        last_seen = max(times).replace(microsecond=0).isoformat()

        v1 = sum(1 for dt in times if dt >= d1)
        v3 = sum(1 for dt in times if dt >= d3)
        v7 = sum(1 for dt in times if dt >= d7)

        watch_hits_count = sum(len(m.get("watch_hits") or []) for m in members)
        category_count = len({m.get("source_category") for m in members if m.get("source_category")})
        diversity = round(len(state.source_ids) / max(1, len(state.item_ids)), 4)
        trend = _trend_score(v1, v3, v7, len(state.source_ids), category_count, watch_hits_count)

        rep = sorted(members, key=lambda x: (x.get("score", 0.0), x.get("published_at") or ""), reverse=True)[0]
        label = _cluster_label(state, members)

        store.upsert_cluster(
            {
                "cluster_id": cid,
                "label": label,
                "created_at": state.created_at,
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "item_count": len(state.item_ids),
                "sources_count": len(state.source_ids),
                "categories": sorted(c for c in state.categories if c),
                "top_tokens": [tok for tok, _ in state.token_counts.most_common(8)],
                "velocity_7d": v7,
                "velocity_3d": v3,
                "velocity_1d": v1,
                "diversity_score": diversity,
                "trend_score": trend,
                "representative_url": rep.get("url"),
                "representative_title": rep.get("title"),
            }
        )

        event_items_added = sum(1 for dt in times if dt.date().isoformat() == date_str)
        event_sources_added = len(
            {
                m.get("source_id")
                for m in members
                if _to_dt(m.get("published_at") or m.get("fetched_at")).date().isoformat() == date_str
            }
        )
        store.upsert_cluster_event(
            cluster_id=cid,
            date_str=date_str,
            items_added=event_items_added,
            sources_added=event_sources_added,
            top_item_id=rep.get("item_id"),
        )

    # Keep clusters bounded to recent months.
    cutoff = (ref_dt - timedelta(days=120)).date().isoformat()
    store.purge_stale_clusters(cutoff)

    return {"items": len(items), "clusters": len(clusters)}
