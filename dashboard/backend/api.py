"""FastAPI app for the Morning Brief dashboard."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from .dao import BriefbotDAO, DashboardConfig
from .llm_adapter import DashboardLLMAdapter


class QueryRequest(BaseModel):
    query: str
    provider: str | None = None
    model: str | None = None


class StoriesQuery(BaseModel):
    source_name: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    limit: int = Field(default=20, ge=5, le=50)
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    watch_hits: list[str] = Field(default_factory=list)
    order: str = "desc"


BASE_DIR = Path(__file__).resolve().parents[2]
if load_dotenv:
    load_dotenv(dotenv_path=os.getenv("BRIEFBOT_ENV_FILE", BASE_DIR / ".env"))
DB_PATH = Path(os.getenv("BRIEFBOT_DB_PATH", BASE_DIR / "data/briefbot.db"))


def _resolve_briefs_dir() -> Path:
    candidates = [
        os.getenv("BRIEFBOT_DASHBOARD_BRIEF_DIR"),
        os.getenv("BRIEFBOT_BRIEF_DIR"),
        str(BASE_DIR / "data/briefs"),
    ]
    fallback = Path(BASE_DIR / "data/briefs")
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and path.is_dir():
            if any(path.glob("*.daily.md")):
                return path
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and path.is_dir():
            return path
    return fallback


BRIEFS_DIR = _resolve_briefs_dir()
logger = logging.getLogger("dashboard.api")

app = FastAPI(title="Morning Brief Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_origin_regex=r"^https://[a-zA-Z0-9.-]+\.ts\.net$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_dao() -> BriefbotDAO:
    return BriefbotDAO(DashboardConfig(db_path=DB_PATH, briefs_dir=BRIEFS_DIR))


@app.middleware("http")
async def log_dashboard_requests(request, call_next):
    response = await call_next(request)
    logger.info(
        "dashboard request method=%s path=%s status=%s host=%s origin=%s referer=%s x_forwarded_uri=%s x_forwarded_prefix=%s x_forwarded_proto=%s",
        request.method,
        request.scope.get("path"),
        response.status_code,
        request.headers.get("host"),
        request.headers.get("origin"),
        request.headers.get("referer"),
        request.headers.get("x-forwarded-uri"),
        request.headers.get("x-forwarded-prefix"),
        request.headers.get("x-forwarded-proto"),
    )
    return response


@app.get("/api/health")
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db_path": str(DB_PATH), "briefs_dir": str(BRIEFS_DIR)}


@app.get("/api/briefs")
@app.get("/briefs")
def list_briefs() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_briefs()
    finally:
        dao.close()


@app.get("/api/briefs/{date_str}")
@app.get("/briefs/{date_str}")
def get_brief(date_str: str) -> dict[str, Any]:
    dao = get_dao()
    try:
        brief = dao.get_brief_markdown(date_str)
    finally:
        dao.close()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@app.get("/api/metrics")
@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.get_metrics()
    finally:
        dao.close()


@app.post("/api/query")
@app.post("/query")
def query_llm(req: QueryRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        provider = req.provider or os.getenv("BRIEFBOT_LLM_PROVIDER", "anthropic")
        model = req.model or os.getenv("BRIEFBOT_MODEL_FOR_SUMMARIES") or os.getenv("BRIEFBOT_LLM_MODEL", "claude-haiku-latest")
        adapter = DashboardLLMAdapter(
            dao=dao,
            provider=provider,
            model=model,
        )
        try:
            result = adapter.answer_query(req.query)
        except Exception as exc:
            result = {
                "query": req.query,
                "tool": None,
                "arguments": {},
                "answer": f"Query execution failed.\n\n{exc}",
                "data": None,
                "error": str(exc),
            }
        history = dao.record_query(
            user_query=req.query,
            llm_response_md=result.get("answer") or "Query failed.",
            tool_name=result.get("tool"),
            tool_args=result.get("arguments") if isinstance(result.get("arguments"), dict) else {},
            tool_result=result.get("data"),
            error=result.get("error"),
            llm_provider=provider,
            llm_model=model,
        )
        result["history_id"] = history.get("id")
        result["created_at"] = history.get("created_at")
        return result
    finally:
        dao.close()


@app.get("/api/queries")
def list_queries(days: int = 14, limit: int = 20) -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_query_history(days=days, limit=min(limit, 20))
    finally:
        dao.close()


@app.get("/api/queries/{query_id}")
def get_query(query_id: str) -> dict[str, Any]:
    dao = get_dao()
    try:
        row = dao.get_query_history_entry(query_id)
    finally:
        dao.close()
    if not row:
        raise HTTPException(status_code=404, detail="Query not found")
    return row


@app.get("/api/stories/sources")
def list_story_sources() -> list[str]:
    dao = get_dao()
    try:
        return dao.list_source_names()
    finally:
        dao.close()


@app.get("/api/stories/clusters")
def list_story_clusters() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_clusters(limit=200)
    finally:
        dao.close()


@app.get("/api/stories/tags")
def list_story_tags() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_tags(days=30, limit=200)
    finally:
        dao.close()


@app.get("/api/stories/watch-hits")
def list_story_watch_hits() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_watch_hits(days=30, limit=200)
    finally:
        dao.close()


@app.post("/api/stories")
def query_stories(req: StoriesQuery) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.query_stories(
            source_name=req.source_name,
            from_date=req.from_date,
            to_date=req.to_date,
            limit=req.limit,
            cluster_id=req.cluster_id,
            tags=req.tags,
            watch_hits=req.watch_hits,
            order=req.order,
        )
    finally:
        dao.close()


@app.get("/api/stories")
def query_stories_get(
    source_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 20,
    cluster_id: str | None = None,
    tags: list[str] | None = None,
    watch_hits: list[str] | None = None,
    order: str = "desc",
) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.query_stories(
            source_name=source_name,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            cluster_id=cluster_id,
            tags=tags or [],
            watch_hits=watch_hits or [],
            order=order,
        )
    finally:
        dao.close()
