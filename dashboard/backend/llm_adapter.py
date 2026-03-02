"""LLM query adapter for dashboard analytics over the briefbot DB."""

from __future__ import annotations

import json
import re
from typing import Any

from briefbot.llm import generate_text

from .dao import BriefbotDAO, serialize_rows

TOOLS = {
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

        if "all items" in low_query or "all stories" in low_query:
            tool_name = "search_items"
            arguments = {"query": "", "days": 30, "limit": 20}

        if tool_name not in TOOLS:
            plan = self._fallback_plan(query)
            tool_name = plan["tool"]
            arguments = plan["arguments"]

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
