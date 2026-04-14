"""LLM query adapter for dashboard analytics over the briefbot DB."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from briefbot.article import get_article_for_item
from briefbot.llm import generate_text
from briefbot.llm import summarize as summarize_article_text

from .dao import BriefbotDAO, serialize_rows

TOOLS = {
    "summarize_article": {
        "description": "Find the best matching item, fetch article text, and return an LLM summary grounded in the article content.",
        "args": {"query": "str"},
    },
    "get_trending_topics": {
        "description": "Get top topic profiles for a recent window.",
        "args": {"days": "int", "limit": "int"},
    },
    "get_trend_clusters": {
        "description": "Get top trend clusters for a recent window.",
        "args": {"days": "int", "limit": "int"},
    },
    "search_items": {
        "description": "Search recent items by text query.",
        "args": {"query": "str", "days": "int", "limit": "int"},
    },
    "get_related_stories": {
        "description": "Find the cluster and related stories for a query/topic.",
        "args": {"query": "str", "days": "int", "limit": "int"},
    },
    "get_news_about": {
        "description": "Find recent items and clusters about a named entity or topic.",
        "args": {"entity": "str", "days": "int", "limit": "int"},
    },
}

SUMMARY_PREFIX_RE = re.compile(r"^\s*(please\s+)?(summari[sz]e|summary(?:\s+of)?)\s+", re.I)


def _clean_summary_query(query: str) -> str:
    cleaned = SUMMARY_PREFIX_RE.sub("", (query or "").strip())
    cleaned = re.sub(r"^\s*(the\s+)?(story|article)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip().strip("\"'`")


def _summary_query_variants(query: str) -> list[str]:
    raw = (query or "").strip()
    if not raw:
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        candidate = (value or "").strip()
        if not candidate:
            return
        key = candidate.lower()
        if key in seen:
            return
        seen.add(key)
        variants.append(candidate)

    add(raw)
    add(_clean_summary_query(raw))
    for quoted in re.findall(r"\"([^\"]+)\"", raw):
        add(quoted.strip())
    if ":" in raw:
        add(raw.split(":", 1)[1].strip())
    return variants


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


def _truncate(text: str | None, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _linkify_markdown(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"(?<!\]\()(?P<url>https?://[^\s)]+)", r"[\g<url>](\g<url>)", text)


def render_items_markdown(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No matching items found."
    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        title = item.get("title") or "(untitled)"
        url = item.get("canonical_url") or item.get("url") or ""
        summary = _truncate(item.get("summary") or item.get("snippet") or "")
        if url:
            line = f"{idx}. [{title}]({url})"
        else:
            line = f"{idx}. {title}"
        if summary:
            line += f" - {summary}"
        lines.append(line)
    return "\n".join(lines)


def _render_named_section(title: str, body: str) -> str:
    if not body.strip():
        return ""
    return f"### {title}\n{body}"


def render_result_markdown(tool_name: str, result: Any) -> str | None:
    if tool_name == "summarize_article" and isinstance(result, dict):
        summary_md = (result.get("summary_md") or "").strip()
        item = result.get("item") or {}
        title = item.get("title") or "(untitled)"
        url = item.get("canonical_url") or item.get("url") or ""
        heading = f"### Summary\n**Title:** [{title}]({url})" if url else f"### Summary\n**Title:** {title}"
        if summary_md:
            return f"{heading}\n\n{summary_md}"
        if result.get("error"):
            return f"{heading}\n\n{result['error']}"

    if tool_name == "search_items" and isinstance(result, list):
        return _render_named_section("Items", render_items_markdown(result))

    if tool_name == "get_news_about" and isinstance(result, dict):
        sections: list[str] = []
        items = result.get("items")
        clusters = result.get("clusters")
        if isinstance(items, list):
            sections.append(_render_named_section("Items", render_items_markdown(items)))
        if isinstance(clusters, list) and clusters:
            cluster_lines = []
            for idx, cluster in enumerate(clusters, start=1):
                label = cluster.get("label") or cluster.get("representative_title") or "general update"
                url = cluster.get("representative_url") or ""
                trend = cluster.get("trend_score")
                if url:
                    cluster_lines.append(f"{idx}. [{label}]({url}) - trend score: {trend}")
                else:
                    cluster_lines.append(f"{idx}. {label} - trend score: {trend}")
            sections.append(_render_named_section("Clusters", "\n".join(cluster_lines)))
        return "\n\n".join(section for section in sections if section)

    if tool_name == "get_related_stories" and isinstance(result, dict):
        sections: list[str] = []
        cluster = result.get("cluster")
        matches = result.get("matches")
        related = result.get("related")
        if cluster:
            label = cluster.get("label") or cluster.get("representative_title") or "general update"
            url = cluster.get("representative_url") or ""
            cluster_line = f"[{label}]({url})" if url else label
            sections.append(_render_named_section("Cluster", cluster_line))
        if isinstance(matches, list):
            sections.append(_render_named_section("Matches", render_items_markdown(matches)))
        if isinstance(related, list):
            sections.append(_render_named_section("Related stories", render_items_markdown(related)))
        return "\n\n".join(section for section in sections if section)

    return None


class DashboardLLMAdapter:
    def __init__(self, dao: BriefbotDAO, provider: str = "anthropic", model: str = "claude-haiku-latest") -> None:
        self.dao = dao
        self.provider = provider
        self.model = model

    def _tool_prompt(self, query: str) -> str:
        return (
            "You route analytics queries onto one database tool.\n"
            "Return JSON only with schema: {\"tool\": \"...\", \"arguments\": {...}}\n"
            "Choose the single best tool. Keep arguments minimal and typed.\n"
            f"Available tools:\n{json.dumps(TOOLS, indent=2)}\n\n"
            f"User query: {query}"
        )

    def _answer_prompt(self, query: str, tool_name: str, result: Any) -> str:
        payload = json.dumps(result, indent=2, ensure_ascii=True)
        return (
            "You answer questions about a Morning Brief database using only the provided tool results.\n"
            "Be concise, factual, and grounded.\n"
            "If the data is sparse or inconclusive, say so.\n"
            "When helpful, use short bullets.\n"
            f"User query: {query}\n"
            f"Tool used: {tool_name}\n"
            f"Tool results:\n{payload}"
        )

    def _fallback_plan(self, query: str) -> dict[str, Any]:
        low = query.lower()
        if "summarize " in low or "summarise " in low or low.startswith("summary of "):
            clean = _clean_summary_query(query)
            return {"tool": "summarize_article", "arguments": {"query": clean or query}}
        if "all items" in low or "all stories" in low:
            return {"tool": "search_items", "arguments": {"query": "", "days": 30, "limit": 20}}
        if "related" in low:
            return {"tool": "get_related_stories", "arguments": {"query": query, "days": 30, "limit": 12}}
        if "last week" in low or "past week" in low or "7 day" in low:
            return {"tool": "get_news_about", "arguments": {"entity": query, "days": 7, "limit": 20}}
        if "trending topic" in low or "topics" in low:
            return {"tool": "get_trending_topics", "arguments": {"days": 30, "limit": 20}}
        if "trend" in low:
            return {"tool": "get_trend_clusters", "arguments": {"days": 30, "limit": 20}}
        return {"tool": "search_items", "arguments": {"query": query, "days": 30, "limit": 20}}

    def _summarize_article(self, query: str) -> dict[str, Any]:
        item = None
        tried = _summary_query_variants(query)
        for candidate in tried:
            item = self.dao.find_best_item_for_query(query=candidate, days=730, limit=160)
            if item:
                break
        if not item:
            return {
                "item": None,
                "summary_md": "",
                "error": f"No matching item found for: {query}",
                "tried_queries": tried,
            }

        cache_dir = os.getenv("BRIEFBOT_CACHE_DIR", "data/article_cache").strip() or "data/article_cache"
        max_chars_raw = os.getenv("BRIEFBOT_MAX_CHARS_PER_ARTICLE", "12000").strip() or "12000"
        try:
            max_chars = int(max_chars_raw)
        except ValueError:
            max_chars = 12000

        fetch_error = None
        try:
            article = get_article_for_item(
                item=item,
                cache_dir=cache_dir,
                force=False,
                max_chars=max_chars,
            )
        except Exception as exc:
            fetch_error = str(exc)
            fallback_text = item.get("summary") or item.get("title") or ""
            article = {
                "url": item.get("canonical_url") or item.get("url"),
                "text": fallback_text,
                "llm_text": fallback_text[:max_chars],
                "snippet": fallback_text[:240],
                "cached": False,
                "content_hash": None,
            }
        metadata = {
            "title": item.get("title"),
            "source_name": item.get("source_name"),
            "source_id": item.get("source_id"),
            "published_at": item.get("published_at"),
            "url": item.get("canonical_url") or item.get("url"),
            "tags": item.get("tags") or [],
            "source_category": item.get("source_category"),
        }
        summary_md = summarize_article_text(
            text=(article.get("llm_text") or article.get("text") or item.get("summary") or "")[:max_chars],
            metadata=metadata,
            provider=self.provider,
            model=self.model,
            max_words=400,
        )
        return {
            "item": item,
            "article": {
                "url": article.get("url") or metadata["url"],
                "snippet": article.get("snippet") or "",
                "cached": bool(article.get("cached")),
                "content_hash": article.get("content_hash"),
            },
            "summary_md": summary_md,
            "error": f"Article fetch fell back to stored metadata: {fetch_error}" if fetch_error else None,
        }

    def answer_query(self, query: str) -> dict[str, Any]:
        low_query = query.lower()
        plan_error = None
        try:
            plan_raw = generate_text(
                prompt=self._tool_prompt(query),
                provider=self.provider,
                model=self.model,
                max_tokens=220,
                temperature=0.0,
            )
            plan = _extract_json(plan_raw)
            tool_name = str(plan.get("tool") or "").strip()
            arguments = plan.get("arguments") if isinstance(plan.get("arguments"), dict) else {}
        except Exception as exc:
            plan_error = str(exc)
            tool_name = ""
            arguments = {}

        if "summarize " in low_query or "summarise " in low_query or low_query.startswith("summary of "):
            plan = self._fallback_plan(query)
            tool_name = plan["tool"]
            arguments = plan["arguments"]

        if "all items" in low_query or "all stories" in low_query:
            tool_name = "search_items"
            arguments = {"query": "", "days": 30, "limit": 20}

        if tool_name not in TOOLS:
            plan = self._fallback_plan(query)
            tool_name = plan["tool"]
            arguments = plan["arguments"]

        if tool_name == "summarize_article":
            result_payload = self._summarize_article(arguments.get("query", query))
        else:
            tool_result = self.dao.execute_tool(tool_name, arguments)
            result_payload = tool_result["result"]
            if isinstance(result_payload, list):
                result_payload = serialize_rows(result_payload)
            elif isinstance(result_payload, dict):
                result_payload = {
                    key: serialize_rows(value) if isinstance(value, list) else value
                    for key, value in result_payload.items()
                }
        deterministic_answer = render_result_markdown(tool_name, result_payload)
        if deterministic_answer:
            return {
                "query": query,
                "tool": tool_name,
                "arguments": arguments,
                "answer": _linkify_markdown(deterministic_answer),
                "data": result_payload,
            }
        try:
            answer = generate_text(
                prompt=self._answer_prompt(query, tool_name, result_payload),
                provider=self.provider,
                model=self.model,
                max_tokens=700,
                temperature=0.1,
            ).strip()
            answer = _linkify_markdown(answer)
        except Exception as exc:
            answer = (
                "LLM synthesis was unavailable, so this is a raw grounded result summary.\n\n"
                f"Tool: {tool_name}\n"
                f"Records returned: {len(result_payload) if isinstance(result_payload, list) else 'see data payload'}\n"
                "Inspect the execution details below for the exact rows."
            )
            if plan_error:
                answer += f"\n\nPlanning error: {plan_error}"
            answer += f"\nAnswer error: {exc}"
            answer = _linkify_markdown(answer)
        return {
            "query": query,
            "tool": tool_name,
            "arguments": arguments,
            "answer": answer,
            "data": result_payload,
        }
