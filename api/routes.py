import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .batches import (
    BatchError,
    batch_lots,
    delete_batch,
    export_csv,
    job_state,
    list_batches,
    lot_variants,
    start_compute,
    upload_batch,
)
from .categories import category_name, list_categories
from .enrichment import DEFAULT_LIMIT, enrichment_state, start_enrichment
from .jobs import enrich_names
from .recommend import fill_names, recommend
from database import database

router = APIRouter(prefix="/match")

_results: dict[str, list[dict]] = {}
_last_request_id: str | None = None


class EnrichmentRequest(BaseModel):
    okpd: str | None = None
    limit: int = DEFAULT_LIMIT


class SearchRequest(BaseModel):
    category: str
    nmck: float = 0
    platform: Literal["ais", "em"] = "ais"
    mspOnly: bool = False
    customerInn: str | None = None


@router.get("/categories")
def categories(q: str = "") -> list[dict]:
    with database.session() as session:
        return list_categories(session, q)


@router.post("/search")
def search_suppliers(request: SearchRequest, background_tasks: BackgroundTasks) -> dict:
    global _last_request_id
    okpd = request.category.strip()
    if not okpd:
        raise HTTPException(422, "Выберите категорию ОКПД2")
    if request.nmck <= 0:
        raise HTTPException(422, "Укажите НМЦК")

    with database.session() as session:
        if category_name(session, okpd) is None:
            raise HTTPException(422, f"Нет такой категории ОКПД2: {okpd}")
        result = recommend(
            session,
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

    return {"requestId": request_id, "total": len(items), "okpd": okpd, "model": result["model"]}


@router.get("/variants")
def variants(requestId: str | None = None) -> dict:
    items = _results.get(requestId or _last_request_id or "", [])
    with database.session() as session:
        return {"items": fill_names(session, items)}


@router.get("/batches")
def batches() -> list[dict]:
    return list_batches()


@router.post("/batches")
def create_batch(files: list[UploadFile] = File(...), name: str = Form("")) -> dict:
    try:
        return upload_batch(name, [(file.filename or "", file.file.read()) for file in files])
    except BatchError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/batches/recompute")
def recompute_batch(name: str) -> dict:
    return {"name": name, "job": start_compute(name)}


@router.get("/batches/status")
def batch_status(name: str) -> dict:
    return {"name": name, "job": job_state(name)}


@router.delete("/batches")
def remove_batch(name: str) -> dict:
    try:
        delete_batch(name)
    except BatchError as error:
        raise HTTPException(422, str(error)) from error
    return {"name": name, "deleted": True}


@router.get("/batches/lots")
def lots_of_batch(name: str) -> dict:
    return {"name": name, "job": job_state(name), "lots": batch_lots(name)}


@router.get("/batches/export")
def export_batch(name: str, top: int = 10) -> Response:
    filename = quote(f"{name}.csv")
    return Response(
        content=export_csv(name, top).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/lots/{lot_id}/variants")
def variants_of_lot(lot_id: int) -> dict:
    result = lot_variants(lot_id)
    if result is None:
        raise HTTPException(404, "Рекомендации для этого лота ещё не рассчитаны")
    return result


@router.post("/enrichment")
def run_enrichment(request: EnrichmentRequest) -> dict:
    okpd = (request.okpd or "").strip() or None
    return start_enrichment(okpd, request.limit)


@router.get("/enrichment")
def enrichment_status() -> dict:
    return enrichment_state()
