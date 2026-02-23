"""Minimal provider abstraction for local summarization calls.

Supports Anthropics and OpenAI chat endpoints via simple HTTPS requests.
"""

from __future__ import annotations

import os
from typing import Any

import requests


def _normalize_model(provider: str, model: str) -> str:
    provider = provider.lower()
    model = (model or "").strip()
    if provider == "anthropic" and model in {"claude-haiku", "claude-haiku-latest", "haiku"}:
        return "claude-3-5-haiku-latest"
    if provider == "openai" and model in {"claude-haiku", "haiku", ""}:
        return "gpt-4o-mini"
    return model or ("claude-haiku-latest" if provider == "anthropic" else "gpt-4o-mini")


def _anthropic_model_candidates(model: str) -> list[str]:
    raw = (model or "").strip()
    if raw in {"", "claude-haiku", "claude-haiku-latest", "haiku"}:
        return [
            # Prefer latest/4.5 style first; fall back to 3.5/3.
            "claude-haiku-latest",
            "claude-4-5-haiku-latest",
            "claude-4.5-haiku-latest",
            "claude-3-5-haiku-latest",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
        ]
    return [_normalize_model("anthropic", raw)]


def _error_detail(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("type")
                if msg:
                    return str(msg)
            if data.get("message"):
                return str(data["message"])
        return str(data)
    except Exception:
        text = (resp.text or "").strip()
        return text[:400] if text else "no response body"


def _prompt(metadata: dict[str, Any], text: str, max_words: int = 400) -> str:
    category = (metadata.get("source_category") or "").lower()
    tags = ", ".join(metadata.get("tags") or [])

    if category == "security":
        lens = "security"
        sections = "What happened; Impact/risk; Technical details; Recommended follow-ups"
    elif category == "papers":
        lens = "research"
        sections = "Core idea; Methods; Results/claims; Why it matters"
    else:
        lens = "product/industry"
        sections = "What changed; Key details; Practical impact; Watch items"

    return (
        f"You are summarizing a morning-brief item for a technical operator.\n"
        f"Use a {lens} lens. Keep under {max_words} words.\n"
        f"Output markdown with bullet points and headings: {sections}.\n"
        f"Do not invent facts. If missing info, say so briefly.\n\n"
        f"Metadata:\n"
        f"- Title: {metadata.get('title')}\n"
        f"- Source: {metadata.get('source_name')} ({metadata.get('source_id')})\n"
        f"- Published: {metadata.get('published_at')}\n"
        f"- Tags: {tags}\n"
        f"- URL: {metadata.get('url')}\n\n"
        f"Content:\n{text}"
    )


def _anthropic_summarize(prompt: str, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    url = os.getenv("BRIEFBOT_ANTHROPIC_URL", "https://api.anthropic.com/v1/messages").strip()
    errors: list[str] = []
    for candidate_model in _anthropic_model_candidates(model):
        resp = requests.post(
            url,
            timeout=60,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": candidate_model,
                "max_tokens": 900,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if resp.status_code >= 400:
            errors.append(f"{candidate_model}: HTTP {resp.status_code} ({_error_detail(resp)})")
            # Try alternate model ids only for 404/400 model-not-found style failures.
            if resp.status_code in {400, 404}:
                continue
            break

        data = resp.json()
        content = data.get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        result = "\n".join(t for t in texts if t).strip()
        if result:
            return result
        errors.append(f"{candidate_model}: empty response content")

    raise RuntimeError("Anthropic request failed. " + " | ".join(errors[:4]))


def _openai_summarize(prompt: str, model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        timeout=60,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _normalize_model("openai", model),
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI response contained no choices")
    msg = (choices[0].get("message") or {}).get("content", "").strip()
    if not msg:
        raise RuntimeError("OpenAI response message was empty")
    return msg


def summarize(
    text: str,
    metadata: dict[str, Any],
    provider: str = "anthropic",
    model: str = "claude-haiku-latest",
    max_words: int = 400,
) -> str:
    provider = (provider or "anthropic").lower()
    prompt = _prompt(metadata=metadata, text=text, max_words=max_words)

    if provider == "anthropic":
        return _anthropic_summarize(prompt, model=model)
    if provider == "openai":
        return _openai_summarize(prompt, model=model)
    raise ValueError(f"Unsupported provider: {provider}")
