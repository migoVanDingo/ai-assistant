"""Streaming client for the raw Anthropic Messages API.

The project intentionally avoids the official SDK (not installed); we speak the
HTTP streaming protocol directly with ``requests`` to match ``briefbot/llm.py``.

``stream_turn`` runs a single assistant turn and yields plain dict events as the
model produces them. The event stream is a sequence of::

    {"type": "text", "text": "..."}          # incremental assistant text
    {"type": "final", "blocks": [...],         # the fully assembled turn
     "stop_reason": "tool_use" | "end_turn" | ...}

``blocks`` is the assistant content in Anthropic message format (``text`` and
``tool_use`` blocks), ready to append back into the conversation.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import requests

from briefbot.llm import _anthropic_model_candidates, _error_detail

ANTHROPIC_VERSION = "2023-06-01"


def _api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return api_key


def _url() -> str:
    return os.getenv("BRIEFBOT_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages").strip()


def stream_turn(
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> Iterator[dict[str, Any]]:
    """Stream one assistant turn, yielding text deltas then a final assembly."""
    api_key = _api_key()
    url = _url()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        "accept": "text/event-stream",
    }

    errors: list[str] = []
    for candidate_model in _anthropic_model_candidates(model):
        payload: dict[str, Any] = {
            "model": candidate_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
        if resp.status_code >= 400:
            detail = _error_detail(resp)
            resp.close()
            errors.append(f"{candidate_model}: HTTP {resp.status_code} ({detail})")
            # Retry alternate model ids only for model-not-found style failures.
            if resp.status_code in {400, 404}:
                continue
            raise RuntimeError("Anthropic stream failed. " + " | ".join(errors))

        yield from _consume_stream(resp)
        return

    raise RuntimeError("Anthropic stream failed. " + " | ".join(errors))


def _consume_stream(resp: requests.Response) -> Iterator[dict[str, Any]]:
    """Parse the SSE byte stream and assemble assistant content blocks."""
    blocks: list[dict[str, Any]] = []
    # Per-index scratch for in-flight blocks: {index: {"type", "text"|"json"...}}
    pending: dict[int, dict[str, Any]] = {}
    stop_reason: str | None = None

    try:
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            data_str = raw_line[len("data:"):].strip()
            if not data_str:
                continue
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            etype = event.get("type")

            if etype == "content_block_start":
                index = event.get("index", 0)
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    pending[index] = {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "json": "",
                    }
                else:
                    pending[index] = {"type": "text", "text": ""}

            elif etype == "content_block_delta":
                index = event.get("index", 0)
                delta = event.get("delta") or {}
                slot = pending.setdefault(index, {"type": "text", "text": ""})
                if delta.get("type") == "text_delta":
                    text = delta.get("text") or ""
                    if text:
                        slot["text"] = slot.get("text", "") + text
                        yield {"type": "text", "text": text}
                elif delta.get("type") == "input_json_delta":
                    slot["json"] = slot.get("json", "") + (delta.get("partial_json") or "")

            elif etype == "content_block_stop":
                index = event.get("index", 0)
                slot = pending.pop(index, None)
                if not slot:
                    continue
                if slot["type"] == "tool_use":
                    try:
                        tool_input = json.loads(slot.get("json") or "{}")
                    except json.JSONDecodeError:
                        tool_input = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": slot.get("id"),
                            "name": slot.get("name"),
                            "input": tool_input if isinstance(tool_input, dict) else {},
                        }
                    )
                else:
                    text = slot.get("text", "")
                    if text:
                        blocks.append({"type": "text", "text": text})

            elif etype == "message_delta":
                delta = event.get("delta") or {}
                if delta.get("stop_reason"):
                    stop_reason = delta.get("stop_reason")

            elif etype == "message_stop":
                break

            elif etype == "error":
                err = event.get("error") or {}
                raise RuntimeError(f"Anthropic stream error: {err.get('message') or err}")
    finally:
        resp.close()

    yield {"type": "final", "blocks": blocks, "stop_reason": stop_reason or "end_turn"}
