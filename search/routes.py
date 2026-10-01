import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from search.categories import detect_okpd
from search.db import connect
from search.jobs import discovery_status, enrich_names, run_discovery, try_start_discovery
from search.recommend import fill_names, recommend

router = APIRouter(prefix="/match")

_results: dict[str, list[dict]] = {}
_last_request_id: str | None = None


class SearchRequest(BaseModel):
    query: str
    nmck: float = 0
    platform: Literal["ais", "em"] = "ais"
    mspOnly: bool = False
    category: str | None = None


class DiscoverRequest(BaseModel):
    query: str
    category: str | None = None


def resolve_okpd(conn, query: str, category: str | None) -> str:
    if category:
        return category[:5]
    candidates = detect_okpd(conn, query)
    if not candidates:
        raise HTTPException(422, "Не удалось определить категорию по описанию, уточните запрос")
    return candidates[0][0]


@router.post("/search")
def search_suppliers(request: SearchRequest, background_tasks: BackgroundTasks) -> dict:
    global _last_request_id
    query = request.query.strip()
    if not query:
        raise HTTPException(422, "Укажите, что вы закупаете")

    with connect() as conn:
        okpd = resolve_okpd(conn, query, request.category)
        result = recommend(conn, query, okpd, eshop=request.platform == "em", msp_only=request.mspOnly)

    items = result["items"]
    request_id = uuid.uuid4().hex
    _results[request_id] = items
    _last_request_id = request_id

    missing_names = [item["inn"] for item in items if item["name"].startswith("Компания ИНН")]
    if missing_names:
        background_tasks.add_task(enrich_names, missing_names)

    return {"requestId": request_id, "total": len(items), "okpd": okpd}


@router.get("/variants")
def variants(requestId: str | None = None) -> dict:
    items = _results.get(requestId or _last_request_id or "", [])
    with connect() as conn:
        return {"items": fill_names(conn, items)}


@router.post("/discover")
def start_discovery(request: DiscoverRequest, background_tasks: BackgroundTasks) -> dict:
    query = request.query.strip()
    if not query:
        raise HTTPException(422, "Укажите, что вы закупаете")
    with connect() as conn:
        okpd = resolve_okpd(conn, query, request.category)
    if try_start_discovery(okpd):
        background_tasks.add_task(run_discovery, query, okpd)
    return {"okpd": okpd, **discovery_status(okpd)}


@router.get("/discover/status")
def get_discovery_status(okpd: str) -> dict:
    return {"okpd": okpd, **discovery_status(okpd)}
