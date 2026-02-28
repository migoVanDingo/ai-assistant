"""FastAPI app for the Morning Brief dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db_path": str(DB_PATH), "briefs_dir": str(BRIEFS_DIR)}


@app.get("/api/briefs")
def list_briefs() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_briefs()
    finally:
        dao.close()


@app.get("/api/briefs/{date_str}")
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
def get_metrics() -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.get_metrics()
    finally:
        dao.close()


@app.post("/api/query")
def query_llm(req: QueryRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        adapter = DashboardLLMAdapter(
            dao=dao,
            provider=req.provider or os.getenv("BRIEFBOT_LLM_PROVIDER", "anthropic"),
            model=req.model or os.getenv("BRIEFBOT_MODEL_FOR_SUMMARIES") or os.getenv("BRIEFBOT_LLM_MODEL", "claude-haiku-latest"),
        )
        return adapter.answer_query(req.query)
    finally:
        dao.close()
