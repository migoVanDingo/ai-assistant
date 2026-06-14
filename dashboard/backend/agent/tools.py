"""Agent tools backed by the existing Briefbot DAO and summarizer.

Each tool is a thin wrapper over a ``BriefbotDAO`` method (or the article
summarizer). Tools expose an Anthropic-format schema and a ``run`` that returns
a JSON-serializable result plus a short human label for the chat UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..dao import BriefbotDAO, serialize_rows
from ..llm_adapter import DashboardLLMAdapter

# Keep tool results small enough to stay cheap for Haiku.
MAX_RESULT_CHARS = 8000


@dataclass
class ToolContext:
    dao: BriefbotDAO
    provider: str
    model: str
    conversation_id: str | None = None


@dataclass
class ToolOutcome:
    result: Any
    summary: str
    # Optional extra SSE events for the loop to forward (e.g. a title change).
    events: list[dict[str, Any]] | None = None


def _serialize(result: Any) -> Any:
    if isinstance(result, list):
        return serialize_rows(result)
    if isinstance(result, dict):
        return {k: serialize_rows(v) if isinstance(v, list) else v for k, v in result.items()}
    return result


def _result_string(result: Any) -> str:
    text = json.dumps(result, ensure_ascii=True, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…(truncated)"
    return text


def _count_label(result: Any, noun: str) -> str:
    if isinstance(result, list):
        return f"{len(result)} {noun}"
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return f"{len(items)} {noun}"
    return noun


class Tool:
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:  # pragma: no cover - interface
        raise NotImplementedError

    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class SearchItems(Tool):
    name = "search_items"
    description = (
        "Search the news/research archive for recent items matching a free-text query. "
        "Returns ranked items with title, url, source, and stored summary. Use an empty "
        "query to list the latest items."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search terms. Empty string lists latest items."},
            "days": {"type": "integer", "description": "Recency window in days (default 30)."},
            "limit": {"type": "integer", "description": "Max results (default 20)."},
        },
        "required": ["query"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        result = _serialize(
            ctx.dao.search_items(
                query=args.get("query", ""),
                days=int(args.get("days", 30) or 30),
                limit=int(args.get("limit", 20) or 20),
            )
        )
        return ToolOutcome(result=result, summary=_count_label(result, "items"))


class GetTrendingTopics(Tool):
    name = "get_trending_topics"
    description = "Get the top trending topics/entities by momentum over a recent window."
    input_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Recency window in days (default 30)."},
            "limit": {"type": "integer", "description": "Max topics (default 20)."},
        },
        "required": [],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        result = _serialize(
            ctx.dao.get_trending_topics(
                days=int(args.get("days", 30) or 30),
                limit=int(args.get("limit", 20) or 20),
            )
        )
        return ToolOutcome(result=result, summary=_count_label(result, "topics"))


class GetTrendClusters(Tool):
    name = "get_trend_clusters"
    description = "Get the top trending storyline clusters by trend score over a recent window."
    input_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Recency window in days (default 30)."},
            "limit": {"type": "integer", "description": "Max clusters (default 20)."},
        },
        "required": [],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        result = _serialize(
            ctx.dao.get_trend_clusters(
                days=int(args.get("days", 30) or 30),
                limit=int(args.get("limit", 20) or 20),
            )
        )
        return ToolOutcome(result=result, summary=_count_label(result, "clusters"))


class GetRelatedStories(Tool):
    name = "get_related_stories"
    description = (
        "Find the best-matching item for a query, its cluster, and the related stories in "
        "that cluster. Use when the user asks for stories related to a topic."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Topic or story to find related stories for."},
            "days": {"type": "integer", "description": "Recency window in days (default 30)."},
            "limit": {"type": "integer", "description": "Max related stories (default 12)."},
        },
        "required": ["query"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        result = _serialize(
            ctx.dao.get_related_stories(
                query=args.get("query", ""),
                days=int(args.get("days", 30) or 30),
                limit=int(args.get("limit", 12) or 12),
            )
        )
        related = result.get("related") if isinstance(result, dict) else None
        summary = f"{len(related)} related" if isinstance(related, list) else "related stories"
        return ToolOutcome(result=result, summary=summary)


class GetNewsAbout(Tool):
    name = "get_news_about"
    description = (
        "Find recent items and clusters about a named entity or topic (e.g. a company, "
        "model, or person). Use for 'what's the news about X' questions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "The entity or topic name."},
            "days": {"type": "integer", "description": "Recency window in days (default 7)."},
            "limit": {"type": "integer", "description": "Max items (default 20)."},
        },
        "required": ["entity"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        result = _serialize(
            ctx.dao.get_news_about(
                entity=args.get("entity", ""),
                days=int(args.get("days", 7) or 7),
                limit=int(args.get("limit", 20) or 20),
            )
        )
        return ToolOutcome(result=result, summary=_count_label(result, "items"))


class SummarizeArticle(Tool):
    name = "summarize_article"
    description = (
        "Find the best-matching archived item for a query (by full or partial title/topic), "
        "fetch the article text, and return a grounded LLM summary. Use when the user asks to "
        "summarize, explain, or break down a specific article or story."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Full or partial title / description of the article to summarize."},
        },
        "required": ["query"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        adapter = DashboardLLMAdapter(dao=ctx.dao, provider=ctx.provider, model=ctx.model)
        result = adapter._summarize_article(args.get("query", ""))
        item = (result or {}).get("item") or {}
        title = item.get("title")
        summary = f"summarized '{title}'" if title else "no matching article"
        # The grounded summary markdown is the useful payload for the model.
        slim = {
            "title": title,
            "url": item.get("canonical_url") or item.get("url"),
            "source_name": item.get("source_name"),
            "published_at": item.get("published_at"),
            "summary_md": result.get("summary_md"),
            "error": result.get("error"),
        }
        return ToolOutcome(result=slim, summary=summary)


class RenameConversation(Tool):
    name = "rename_conversation"
    description = (
        "Rename the current chat conversation. Use when the user asks to rename, retitle, or "
        "call this chat something specific."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The new conversation title (keep it short)."},
        },
        "required": ["title"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        title = (args.get("title") or "").strip()[:80]
        if not ctx.conversation_id or not title:
            return ToolOutcome(result={"error": "missing conversation or title"}, summary="rename failed")
        ctx.dao.set_conversation_title(ctx.conversation_id, title)
        return ToolOutcome(
            result={"renamed": True, "title": title},
            summary=f"renamed to '{title}'",
            events=[{"type": "title", "title": title}],
        )


class CreateFavoriteFolder(Tool):
    name = "create_favorite_folder"
    description = (
        "Create a favorites folder (collection) by name. Idempotent: returns the existing folder "
        "if one with that name already exists."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The folder name, e.g. 'security'."},
        },
        "required": ["name"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        name = (args.get("name") or "").strip()
        if not name:
            return ToolOutcome(result={"error": "folder name is required"}, summary="missing name")
        folder = ctx.dao.create_favorite_folder(name)
        return ToolOutcome(result=folder, summary=f"folder '{name}' ready")


class AddFavorite(Tool):
    name = "add_favorite"
    description = (
        "Save an article to a favorites folder. Identify the article with `query` (a title or "
        "topic to locate it in the archive — e.g. one just discussed in this chat) or by passing "
        "`url` and `title` directly. `folder` is the folder name (defaults to 'favorites'); the "
        "folder is created automatically if it doesn't exist."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Title or topic of the article to find and save."},
            "url": {"type": "string", "description": "Explicit article URL (use when not searching by query)."},
            "title": {"type": "string", "description": "Explicit article title (pairs with url)."},
            "folder": {"type": "string", "description": "Folder name to save into (default 'favorites')."},
        },
        "required": [],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        folder_name = (args.get("folder") or "favorites").strip() or "favorites"
        folder = ctx.dao.get_favorite_folder_by_name(folder_name) or ctx.dao.create_favorite_folder(folder_name)
        folder_id = folder.get("folder_id")

        query = (args.get("query") or "").strip()
        url = (args.get("url") or "").strip()
        title = (args.get("title") or "").strip()
        item_id = None

        if query and not url:
            item = ctx.dao.find_best_item_for_query(query=query, days=730, limit=160)
            if item:
                title = item.get("title") or title
                url = item.get("canonical_url") or item.get("url") or url
                item_id = item.get("item_id")

        if not url:
            return ToolOutcome(
                result={"error": f"could not find an article to add for: {query or '(none)'}"},
                summary="article not found",
            )

        saved = ctx.dao.add_favorite_link(title=title or url, url=url, folder_id=folder_id, item_id=item_id)
        return ToolOutcome(
            result={"folder": folder_name, "title": saved.get("title"), "url": saved.get("url")},
            summary=f"saved to '{folder_name}'",
        )


class ListFavorites(Tool):
    name = "list_favorites"
    description = (
        "List the saved articles in a favorites folder. `folder` is the folder name (defaults to "
        "'favorites'). Use for 'what's in my X folder' questions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Folder name to list (default 'favorites')."},
        },
        "required": [],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        folder_name = (args.get("folder") or "favorites").strip() or "favorites"
        folder = ctx.dao.get_favorite_folder_by_name(folder_name)
        if not folder:
            available = [f.get("name") for f in ctx.dao.list_favorite_folders()]
            return ToolOutcome(
                result={"error": f"no folder named '{folder_name}'", "available_folders": available},
                summary="folder not found",
            )
        listing = ctx.dao.list_favorite_links(folder_id=folder.get("folder_id"))
        items = [
            {"title": row.get("title"), "url": row.get("url")}
            for row in listing.get("items", [])
        ]
        return ToolOutcome(
            result={"folder": folder_name, "items": items},
            summary=f"{len(items)} in '{folder_name}'",
        )


class RemoveFavorite(Tool):
    name = "remove_favorite"
    description = (
        "Remove a saved article from a favorites folder. Identify the article with `query` (a "
        "title/topic to locate it) or an explicit `url`. `folder` is the folder name (defaults to "
        "'favorites')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Title or topic of the saved article to remove."},
            "url": {"type": "string", "description": "Explicit URL of the saved article to remove."},
            "folder": {"type": "string", "description": "Folder name to remove from (default 'favorites')."},
        },
        "required": [],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        folder_name = (args.get("folder") or "favorites").strip() or "favorites"
        folder = ctx.dao.get_favorite_folder_by_name(folder_name)
        if not folder:
            available = [f.get("name") for f in ctx.dao.list_favorite_folders()]
            return ToolOutcome(
                result={"error": f"no folder named '{folder_name}'", "available_folders": available},
                summary="folder not found",
            )

        candidate_urls: list[str] = []
        url = (args.get("url") or "").strip()
        query = (args.get("query") or "").strip()
        if url:
            candidate_urls.append(url)
        elif query:
            item = ctx.dao.find_best_item_for_query(query=query, days=730, limit=160)
            if item:
                for candidate in (item.get("canonical_url"), item.get("url")):
                    if candidate and candidate not in candidate_urls:
                        candidate_urls.append(candidate)

        if not candidate_urls:
            return ToolOutcome(
                result={"error": f"could not identify an article to remove for: {query or url or '(none)'}"},
                summary="article not found",
            )

        for candidate in candidate_urls:
            try:
                ctx.dao.remove_favorite_link(folder_id=folder["folder_id"], url=candidate)
                return ToolOutcome(
                    result={"removed": True, "folder": folder_name, "url": candidate},
                    summary=f"removed from '{folder_name}'",
                )
            except ValueError:
                continue
        return ToolOutcome(
            result={"error": f"that article is not saved in '{folder_name}'"},
            summary="not in folder",
        )


class DeleteFavoriteFolder(Tool):
    name = "delete_favorite_folder"
    description = (
        "Delete a favorites folder and everything saved in it. The default 'favorites' folder "
        "cannot be deleted. Use only when the user clearly asks to delete a whole folder."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The folder name to delete."},
        },
        "required": ["name"],
    }

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        name = (args.get("name") or "").strip()
        try:
            result = ctx.dao.delete_favorite_folder(name)
        except ValueError as exc:
            return ToolOutcome(result={"error": str(exc)}, summary="cannot delete")
        if not result.get("removed"):
            return ToolOutcome(result=result, summary=f"no folder '{name}'")
        return ToolOutcome(result=result, summary=f"deleted '{name}'")


class ListFavoriteFolders(Tool):
    name = "list_favorite_folders"
    description = "List the user's favorites folders and how many articles each holds."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
        folders = [
            {"name": f.get("name"), "count": f.get("count")}
            for f in ctx.dao.list_favorite_folders()
        ]
        return ToolOutcome(result={"folders": folders}, summary=f"{len(folders)} folders")


_TOOL_CLASSES: list[type[Tool]] = [
    SearchItems,
    GetTrendingTopics,
    GetTrendClusters,
    GetRelatedStories,
    GetNewsAbout,
    SummarizeArticle,
    RenameConversation,
    CreateFavoriteFolder,
    AddFavorite,
    ListFavorites,
    RemoveFavorite,
    DeleteFavoriteFolder,
    ListFavoriteFolders,
]


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._by_name = {tool.name: tool for tool in tools}

    def get(self, name: str) -> Tool | None:
        return self._by_name.get(name)

    def anthropic_schemas(self) -> list[dict[str, Any]]:
        return [tool.anthropic_schema() for tool in self._by_name.values()]

    def execute(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> ToolOutcome:
        tool = self.get(name)
        if tool is None:
            return ToolOutcome(result={"error": f"unknown tool: {name}"}, summary="unknown tool")
        return tool.run(ctx, args or {})


def build_registry() -> ToolRegistry:
    return ToolRegistry([cls() for cls in _TOOL_CLASSES])


def result_to_content(result: Any) -> str:
    """Render a tool result into the string fed back to the model."""
    return _result_string(result)
