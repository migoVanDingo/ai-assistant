"""Multi-turn tool-use chat loop, streamed as plain dict events.

``run_chat_turn`` is a synchronous generator. The API layer wraps it in a
Starlette ``StreamingResponse`` (which iterates sync generators in a threadpool),
so the blocking ``requests`` calls and the per-thread sqlite connection are safe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from briefbot.llm import generate_text

from ..dao import BriefbotDAO
from .anthropic_stream import stream_turn
from .tools import ToolContext, build_registry, result_to_content

MAX_ITERATIONS = 12


def _system_prompt() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        "You are Briefbot, a research assistant embedded in a personal news/research "
        "dashboard. You help the user explore an archive of papers, blog posts, and tech/"
        "security news, and you summarize specific articles on request.\n\n"
        f"Today's date is {today}.\n\n"
        "Use the provided tools to ground every factual answer in the archive — never invent "
        "stories, titles, or links. Call tools as needed (you may call several across turns) "
        "before answering. When you reference a story, include its markdown link so the user "
        "can click through. Prefer summarize_article when the user wants a specific article "
        "explained.\n\n"
        "Be concise and conversational. Format answers in markdown with short bullets and "
        "headings where helpful. If the archive has nothing relevant, say so plainly."
    )


def _history_to_messages(dao: BriefbotDAO, conversation_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for row in dao.get_conversation_messages(conversation_id):
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def _generate_title(user_text: str, provider: str, model: str) -> str:
    prompt = (
        "Write a short, specific title (max 6 words) for a chat that starts with this "
        "message. Return only the title, no quotes or punctuation at the end.\n\n"
        f"Message: {user_text}"
    )
    try:
        title = generate_text(
            prompt=prompt, provider=provider, model=model, max_tokens=24, temperature=0.2
        ).strip()
    except Exception:
        title = ""
    title = title.strip().strip("\"'`").splitlines()[0] if title else ""
    if not title:
        title = (user_text or "New chat").strip()
    return title[:80]


def run_chat_turn(
    *,
    dao: BriefbotDAO,
    conversation_id: str,
    user_text: str,
    provider: str,
    model: str,
) -> Iterator[dict[str, Any]]:
    meta = dao.get_conversation_meta(conversation_id)
    if not meta:
        yield {"type": "error", "message": "conversation not found"}
        return

    needs_title = not (meta.get("title") or "").strip()
    dao.append_message(conversation_id=conversation_id, role="user", content=user_text)

    messages = _history_to_messages(dao, conversation_id)
    registry = build_registry()
    ctx = ToolContext(dao=dao, provider=provider, model=model, conversation_id=conversation_id)
    tools = registry.anthropic_schemas()
    system = _system_prompt()

    assistant_text = ""
    tool_call_log: list[dict[str, Any]] = []

    for _ in range(MAX_ITERATIONS):
        blocks: list[dict[str, Any]] = []
        stop_reason = "end_turn"
        for event in stream_turn(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=1500,
            temperature=0.3,
        ):
            if event["type"] == "text":
                assistant_text += event["text"]
                yield {"type": "token", "text": event["text"]}
            elif event["type"] == "final":
                blocks = event["blocks"]
                stop_reason = event["stop_reason"]

        messages.append({"role": "assistant", "content": blocks})

        if stop_reason != "tool_use":
            break

        tool_results: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            args = block.get("input") or {}
            yield {"type": "tool_start", "id": block.get("id"), "name": name, "input": args}
            outcome = registry.execute(ctx, name, args)
            yield {"type": "tool_end", "id": block.get("id"), "name": name, "summary": outcome.summary}
            for extra in outcome.events or []:
                yield extra
            tool_call_log.append({"name": name, "summary": outcome.summary})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": result_to_content(outcome.result),
                }
            )
        messages.append({"role": "user", "content": tool_results})
    else:
        note = "\n\n_(Stopped after reaching the tool-call limit.)_"
        assistant_text += note
        yield {"type": "token", "text": note}

    final_text = assistant_text.strip() or "_(No response generated.)_"
    saved = dao.append_message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_text,
        tool_calls=tool_call_log or None,
    )

    # Only auto-title if the conversation still has no title — e.g. the agent may
    # have set one mid-turn via the rename_conversation tool.
    if needs_title:
        current = dao.get_conversation_meta(conversation_id) or {}
        if not (current.get("title") or "").strip():
            title = _generate_title(user_text, provider, model)
            dao.set_conversation_title(conversation_id, title)
            yield {"type": "title", "title": title}

    yield {"type": "done", "conversation_id": conversation_id, "message_id": saved.get("id")}
