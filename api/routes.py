import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .categories import category_name, list_categories
from .db import connect
from .jobs import enrich_names, find_new_suppliers
from .recommend import fill_names, recommend

router = APIRouter(prefix="/match")

_results: dict[str, list[dict]] = {}
_last_request_id: str | None = None


class SearchRequest(BaseModel):
    category: str
    nmck: float = 0
    platform: Literal["ais", "em"] = "ais"
    mspOnly: bool = False
    searchNew: bool = False
    customerInn: str | None = None


@router.get("/categories")
def categories(q: str = "") -> list[dict]:
    with connect() as conn:
        return list_categories(conn, q)


@router.post("/search")
def search_suppliers(request: SearchRequest, background_tasks: BackgroundTasks) -> dict:
    global _last_request_id
    okpd = request.category.strip()
    if not okpd:
        raise HTTPException(422, "Выберите категорию ОКПД2")
    if request.nmck <= 0:
        raise HTTPException(422, "Укажите НМЦК")

    with connect() as conn:
        name = category_name(conn, okpd)
        if name is None:
            raise HTTPException(422, f"Нет такой категории ОКПД2: {okpd}")
        new_found = find_new_suppliers(conn, okpd, name) if request.searchNew else 0
        result = recommend(
            conn,
            okpd,
            request.nmck,
            eshop=request.platform == "em",
            msp_only=request.mspOnly,
            customer_inn=(request.customerInn or "").strip() or None,
        )

    items = result["items"]
    request_id = uuid.uuid4().hex
    _results[request_id] = items
    _last_request_id = request_id

    missing_names = [item["inn"] for item in items if item["name"].startswith("Компания ИНН")]
    if missing_names:
        background_tasks.add_task(enrich_names, missing_names)

    return {"requestId": request_id, "total": len(items), "okpd": okpd, "newFound": new_found, "model": result["model"]}


@router.get("/variants")
def variants(requestId: str | None = None) -> dict:
    items = _results.get(requestId or _last_request_id or "", [])
    with connect() as conn:
        return {"items": fill_names(conn, items)}
