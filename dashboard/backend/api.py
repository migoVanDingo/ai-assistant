"""FastAPI app for the Morning Brief dashboard."""

from __future__ import annotations

import json
import os
import logging
import re
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import feedparser
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from briefbot.normalize import normalize_arxiv_entry
from briefbot.opportunity import compute_opportunity
from briefbot.score import compute_score
from briefbot.store import Store
from briefbot.watchlist import load_watchlist, match_watchlist

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
    search: str | None = None
    limit: int = Field(default=20, ge=5, le=50)
    cluster_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    watch_hits: list[str] = Field(default_factory=list)
    order: str = "desc"


class StoryFeedbackRequest(BaseModel):
    item_id: str
    vote: int = Field(ge=-1, le=1)
    section: str = "other_links"


class StoryLinksResolveRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)


class FavoriteFolderCreateRequest(BaseModel):
    name: str


class FavoriteAddRequest(BaseModel):
    title: str
    url: str
    folder_id: str | None = None
    item_id: str | None = None


class NightlyRunRequest(BaseModel):
    mode: str = Field(default="standard")


class ArxivImportRequest(BaseModel):
    url: str


BASE_DIR = Path(__file__).resolve().parents[2]
if load_dotenv:
    load_dotenv(dotenv_path=os.getenv("BRIEFBOT_ENV_FILE", BASE_DIR / ".env"))
DB_PATH = Path(os.getenv("BRIEFBOT_DB_PATH", BASE_DIR / "data/briefbot.db"))
LOG_DIR = Path(os.getenv("BRIEFBOT_LOG_DIR", BASE_DIR / "data/logs"))
NIGHTLY_SCRIPT = BASE_DIR / "briefbot/nightly_briefbot.sh"
WATCHLIST_PATH = Path(os.getenv("BRIEFBOT_WATCHLIST_PATH", BASE_DIR / "watchlist.yaml"))

NIGHTLY_JOB_LOCK = threading.Lock()
NIGHTLY_JOB_STATE: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "run_id": None,
    "mode": None,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "log_path": None,
    "command": None,
    "error": None,
}
NIGHTLY_MODES = {"standard", "arxiv_backfill_2y"}
ARXIV_ID_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z.\-]+/\d{7})(?:v\d+)?$")


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _snapshot_nightly_job() -> dict[str, Any]:
    with NIGHTLY_JOB_LOCK:
        return dict(NIGHTLY_JOB_STATE)


def _nightly_env_for_mode(mode: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PROJECT_DIR"] = str(BASE_DIR)
    env["BRIEFBOT_DIR"] = str(BASE_DIR)
    if mode == "arxiv_backfill_2y":
        env["BRIEFBOT_ARXIV_LOOKBACK_DAYS"] = "730"
        env.setdefault("BRIEFBOT_ARXIV_MAX_RESULTS_TOTAL", "50000")
    return env


def _run_nightly_job(run_id: str, mode: str, log_path: Path) -> None:
    command = ["/bin/bash", str(NIGHTLY_SCRIPT)]
    env = _nightly_env_for_mode(mode)
    started_at = _utc_now_iso()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with NIGHTLY_JOB_LOCK:
        NIGHTLY_JOB_STATE.update(
            {
                "running": True,
                "status": "running",
                "run_id": run_id,
                "mode": mode,
                "started_at": started_at,
                "finished_at": None,
                "exit_code": None,
                "log_path": str(log_path),
                "command": command,
                "error": None,
            }
        )

    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "event": "dashboard_manual_nightly_start",
                        "run_id": run_id,
                        "mode": mode,
                        "started_at": started_at,
                        "command": command,
                        "cwd": str(BASE_DIR),
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )
            handle.flush()
            completed = subprocess.run(
                command,
                cwd=str(BASE_DIR),
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        finished_at = _utc_now_iso()
        with NIGHTLY_JOB_LOCK:
            NIGHTLY_JOB_STATE.update(
                {
                    "running": False,
                    "status": "success" if completed.returncode == 0 else "failed",
                    "finished_at": finished_at,
                    "exit_code": completed.returncode,
                    "error": None,
                }
            )
    except Exception as exc:  # pragma: no cover - defensive guard for background thread
        finished_at = _utc_now_iso()
        with NIGHTLY_JOB_LOCK:
            NIGHTLY_JOB_STATE.update(
                {
                    "running": False,
                    "status": "failed",
                    "finished_at": finished_at,
                    "exit_code": -1,
                    "error": str(exc),
                }
            )


def _extract_arxiv_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("arXiv URL is required")
    parsed = urlparse(raw)
    candidate = raw
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        if "arxiv.org" not in host:
            raise ValueError("URL must be from arxiv.org")
        path = (parsed.path or "").strip("/")
        if path.startswith("abs/"):
            candidate = path.split("/", 1)[1]
        elif path.startswith("pdf/"):
            candidate = path.split("/", 1)[1]
        else:
            candidate = path
    candidate = candidate.strip()
    if candidate.lower().startswith("arxiv:"):
        candidate = candidate.split(":", 1)[1].strip()
    if candidate.lower().endswith(".pdf"):
        candidate = candidate[:-4]
    candidate = candidate.strip("/")
    if not ARXIV_ID_RE.match(candidate):
        raise ValueError(f"Could not parse a valid arXiv id from: {value}")
    return candidate


def _fetch_arxiv_entry(arxiv_id: str) -> dict[str, Any]:
    api_url = f"https://export.arxiv.org/api/query?id_list={quote_plus(arxiv_id)}"
    response = requests.get(api_url, timeout=20, headers={"User-Agent": "briefbot-dashboard/1.0"})
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    entries = list(parsed.entries or [])
    if not entries:
        raise ValueError(f"No arXiv entry found for id: {arxiv_id}")
    return dict(entries[0])

app = FastAPI(title="Morning Brief Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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
@app.get("/queries")
def list_queries(days: int = 14, limit: int = 20) -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_query_history(days=days, limit=min(limit, 20))
    finally:
        dao.close()


@app.get("/api/queries/{query_id}")
@app.get("/queries/{query_id}")
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
@app.get("/stories/sources")
def list_story_sources() -> list[str]:
    dao = get_dao()
    try:
        return dao.list_source_names()
    finally:
        dao.close()


@app.get("/api/stories/clusters")
@app.get("/stories/clusters")
def list_story_clusters() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_clusters(limit=200)
    finally:
        dao.close()


@app.get("/api/stories/tags")
@app.get("/stories/tags")
def list_story_tags() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_tags(days=30, limit=200)
    finally:
        dao.close()


@app.get("/api/stories/watch-hits")
@app.get("/stories/watch-hits")
def list_story_watch_hits() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_watch_hits(days=30, limit=200)
    finally:
        dao.close()


@app.post("/api/stories")
@app.post("/stories")
def query_stories(req: StoriesQuery) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.query_stories(
            source_name=req.source_name,
            from_date=req.from_date,
            to_date=req.to_date,
            search=req.search,
            limit=req.limit,
            cluster_id=req.cluster_id,
            tags=req.tags,
            watch_hits=req.watch_hits,
            order=req.order,
        )
    finally:
        dao.close()


@app.get("/api/stories/sections")
@app.get("/stories/sections")
def list_story_sections(section_limit: int = 12) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.list_story_sections(section_limit=section_limit)
    finally:
        dao.close()


@app.post("/api/stories/feedback")
@app.post("/stories/feedback")
def set_story_feedback(req: StoryFeedbackRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.set_story_feedback(item_id=req.item_id, vote=req.vote, section=req.section)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        dao.close()


@app.post("/api/stories/resolve-links")
@app.post("/stories/resolve-links")
def resolve_story_links(req: StoryLinksResolveRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        return {"items": dao.resolve_story_links(req.urls)}
    finally:
        dao.close()


@app.get("/api/favorites/folders")
@app.get("/favorites/folders")
def list_favorite_folders() -> list[dict[str, Any]]:
    dao = get_dao()
    try:
        return dao.list_favorite_folders()
    finally:
        dao.close()


@app.post("/api/favorites/folders")
@app.post("/favorites/folders")
def create_favorite_folder(req: FavoriteFolderCreateRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.create_favorite_folder(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        dao.close()


@app.post("/api/favorites/items")
@app.post("/favorites/items")
def add_favorite_item(req: FavoriteAddRequest) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.add_favorite_link(
            title=req.title,
            url=req.url,
            folder_id=req.folder_id,
            item_id=req.item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        dao.close()


@app.get("/api/favorites/items")
@app.get("/favorites/items")
def list_favorite_items(folder_id: str | None = None) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.list_favorite_links(folder_id=folder_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        dao.close()


@app.delete("/api/favorites/items")
@app.delete("/favorites/items")
def remove_favorite_item(
    favorite_id: str | None = None,
    folder_id: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    dao = get_dao()
    try:
        return dao.remove_favorite_link(favorite_id=favorite_id, folder_id=folder_id, url=url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        dao.close()


@app.get("/api/stories")
@app.get("/stories")
def query_stories_get(
    source_name: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = None,
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
            search=search,
            limit=limit,
            cluster_id=cluster_id,
            tags=tags or [],
            watch_hits=watch_hits or [],
            order=order,
        )
    finally:
        dao.close()


@app.get("/api/jobs/nightly")
def get_nightly_job_status() -> dict[str, Any]:
    return _snapshot_nightly_job()


@app.post("/api/jobs/nightly")
def run_nightly_job(req: NightlyRunRequest) -> dict[str, Any]:
    mode = (req.mode or "standard").strip().lower()
    if mode not in NIGHTLY_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode}'. Expected one of: {sorted(NIGHTLY_MODES)}")
    if not NIGHTLY_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Nightly script not found: {NIGHTLY_SCRIPT}")

    with NIGHTLY_JOB_LOCK:
        if NIGHTLY_JOB_STATE.get("running"):
            active = dict(NIGHTLY_JOB_STATE)
            raise HTTPException(
                status_code=409,
                detail=f"Nightly run already in progress (run_id={active.get('run_id')}, mode={active.get('mode')})",
            )
        run_id = str(uuid.uuid4())
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = "backfill2y" if mode == "arxiv_backfill_2y" else "standard"
        log_path = LOG_DIR / f"manual-nightly.{stamp}.{suffix}.{run_id[:8]}.log"
        NIGHTLY_JOB_STATE.update(
            {
                "running": True,
                "status": "running",
                "run_id": run_id,
                "mode": mode,
                "started_at": _utc_now_iso(),
                "finished_at": None,
                "exit_code": None,
                "log_path": str(log_path),
                "command": ["/bin/bash", str(NIGHTLY_SCRIPT)],
                "error": None,
            }
        )

    thread = threading.Thread(
        target=_run_nightly_job,
        args=(run_id, mode, log_path),
        daemon=True,
        name=f"dashboard-nightly-{run_id[:8]}",
    )
    thread.start()
    return _snapshot_nightly_job()


@app.post("/api/arxiv/import")
def import_arxiv_paper(req: ArxivImportRequest) -> dict[str, Any]:
    try:
        arxiv_id = _extract_arxiv_id(req.url)
        entry = _fetch_arxiv_entry(arxiv_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch arXiv metadata: {exc}") from exc

    primary_category = entry.get("arxiv_primary_category")
    if isinstance(primary_category, dict):
        primary_category = primary_category.get("term")
    primary_category = (str(primary_category or "").strip() or None)
    tags = ["papers", "arxiv", "manual"]
    if primary_category:
        tags.append(primary_category.lower())

    source = {
        "id": "arxiv_manual_import",
        "name": "arXiv Manual Import",
        "mode": "query",
        "query": f"id:{arxiv_id}",
        "tags": tags,
        "category": "papers",
        "tier": 1,
        "max_daily": None,
        "weight": 1.0,
    }
    item = normalize_arxiv_entry(source, entry)
    watchlist = load_watchlist(WATCHLIST_PATH)
    watch_hits = match_watchlist(item.get("title"), item.get("summary"), watchlist)
    item["watch_hits"] = watch_hits
    if watch_hits:
        raw = dict(item.get("raw") or {})
        raw["watch_hits"] = watch_hits
        item["raw"] = raw
    item["score"] = compute_score(item, source_weight=float(source.get("weight") or 1.0))
    opp = compute_opportunity(item)
    item.update(
        {
            "score_opportunity": opp.get("score_opportunity"),
            "opportunity_reason": opp.get("opportunity_reason"),
            "opportunity_tags": opp.get("opportunity_tags", []),
        }
    )
    if opp.get("components"):
        raw = dict(item.get("raw") or {})
        raw["opportunity_components"] = opp["components"]
        item["raw"] = raw

    store = Store(DB_PATH)
    try:
        upsert_result = store.upsert_item(item)
    finally:
        store.close()
    return {
        "arxiv_id": arxiv_id,
        "inserted": bool(upsert_result.inserted),
        "duplicate": bool(upsert_result.duplicate),
        "item": {
            "item_id": item.get("item_id"),
            "title": item.get("title"),
            "url": item.get("canonical_url") or item.get("url"),
            "published_at": item.get("published_at"),
            "source_name": item.get("source_name"),
            "tags": item.get("tags") or [],
        },
        "note": "Imported into the archive. Cluster/trend sections update after the next collect+cluster run.",
    }
