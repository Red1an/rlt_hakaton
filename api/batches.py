import csv
import io
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, distinct, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database import (
    AnnouncementModel,
    LotModel,
    LotRecommendationModel,
    database,
)
from parser.load import HISTORY_DATASET, collect_sources, load_sources

from .jobs import enrich_names
from .recommend import fill_names, recommend

TOP_PREVIEW = 3
TOP_EXPORT = 10
NAMES_PER_LOT = 10

EXPORT_COLUMNS = [
    "lot_id", "publish_date", "subject", "customer_inn", "start_price", "platform", "only_msp",
    "rank", "supplier_inn", "supplier_name", "novelty", "role", "score",
    "competitive_bids", "competitive_wins", "direct_contracts", "last_bid", "reasons",
]

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


class BatchError(ValueError):
    pass


def job_state(dataset: str) -> dict:
    return _jobs.get(dataset, {"status": "idle"})


def batches_stmt():
    return (
        select(
            AnnouncementModel.dataset.label("dataset"),
            func.count().label("lots"),
            func.count(LotRecommendationModel.lot_id).label("computed"),
            func.min(AnnouncementModel.publish_date).label("date_from"),
            func.max(AnnouncementModel.publish_date).label("date_to"),
            func.max(LotRecommendationModel.computed_at).label("computed_at"),
        )
        .select_from(AnnouncementModel)
        .outerjoin(LotRecommendationModel, LotRecommendationModel.lot_id == AnnouncementModel.lot_id)
        .where(AnnouncementModel.dataset != HISTORY_DATASET)
        .group_by(AnnouncementModel.dataset)
        .order_by(func.max(AnnouncementModel.publish_date).desc(), AnnouncementModel.dataset)
    )


def lots_stmt(dataset: str):
    dataset_lots = select(AnnouncementModel.lot_id).where(AnnouncementModel.dataset == dataset)
    groups = (
        select(
            LotModel.lot_id,
            func.array_agg(distinct(func.left(LotModel.okpd_code, 5))).label("groups"),
            func.mode().within_group(func.left(LotModel.okpd_code, 5)).label("main_group"),
        )
        .where(
            LotModel.okpd_code.regexp_match(r"^\d{2}\.\d{2}"),
            LotModel.lot_id.in_(dataset_lots),
        )
        .group_by(LotModel.lot_id)
        .subquery()
    )
    return (
        select(
            AnnouncementModel.lot_id,
            AnnouncementModel.publish_date,
            AnnouncementModel.start_price,
            AnnouncementModel.subject,
            AnnouncementModel.is_smp,
            AnnouncementModel.customer_inn,
            AnnouncementModel.is_eshop_or_aisgz.label("is_eshop"),
            func.coalesce(groups.c.groups, literal_column("ARRAY[]::text[]")).label("groups"),
            groups.c.main_group.label("main_group"),
            LotRecommendationModel.items,
            LotRecommendationModel.computed_at,
        )
        .select_from(AnnouncementModel)
        .outerjoin(groups, groups.c.lot_id == AnnouncementModel.lot_id)
        .outerjoin(LotRecommendationModel, LotRecommendationModel.lot_id == AnnouncementModel.lot_id)
        .where(AnnouncementModel.dataset == dataset)
        .order_by(AnnouncementModel.publish_date, AnnouncementModel.lot_id)
    )


def upsert_stmt(lot_id: int, items: list[dict]):
    stmt = pg_insert(LotRecommendationModel).values(lot_id=lot_id, items=items, computed_at=func.now())
    return stmt.on_conflict_do_update(
        index_elements=[LotRecommendationModel.lot_id],
        set_={"items": stmt.excluded.items, "computed_at": stmt.excluded.computed_at},
    )


def delete_stmts(dataset: str) -> list:
    dataset_lots = select(AnnouncementModel.lot_id).where(AnnouncementModel.dataset == dataset)
    return [
        delete(LotModel).where(LotModel.lot_id.in_(dataset_lots)),
        delete(AnnouncementModel).where(AnnouncementModel.dataset == dataset),
    ]


def list_batches() -> list[dict]:
    with database.session() as session:
        rows = [dict(row) for row in session.execute(batches_stmt()).mappings()]
    return [
        {
            "name": row["dataset"],
            "lots": row["lots"],
            "computed": row["computed"],
            "dateFrom": row["date_from"].isoformat() if row["date_from"] else None,
            "dateTo": row["date_to"].isoformat() if row["date_to"] else None,
            "computedAt": row["computed_at"].isoformat() if row["computed_at"] else None,
            "job": job_state(row["dataset"]),
        }
        for row in rows
    ]


def load_lots(session: Session, dataset: str) -> list[dict]:
    return [dict(row) for row in session.execute(lots_stmt(dataset)).mappings()]


def lot_summary(lot: dict) -> dict:
    items = lot["items"] or []
    return {
        "lotId": lot["lot_id"],
        "publishDate": lot["publish_date"].isoformat(),
        "subject": lot["subject"],
        "customerInn": lot["customer_inn"],
        "nmck": lot["start_price"],
        "platform": "em" if lot["is_eshop"] else "ais",
        "mspOnly": lot["is_smp"],
        "categories": sorted(lot["groups"]),
        "computed": lot["items"] is not None,
        "total": len(items),
        "top": [
            {"inn": item["inn"], "name": item["name"], "score": item["score"], "novelty": item["novelty"]}
            for item in items[:TOP_PREVIEW]
        ],
    }


def batch_lots(dataset: str) -> list[dict]:
    with database.session() as session:
        lots = load_lots(session, dataset)
        for lot in lots:
            if lot["items"]:
                fill_names(session, lot["items"][:TOP_PREVIEW])
    return [lot_summary(lot) for lot in lots]


def compute_lot(session: Session, lot: dict) -> list[dict]:
    if not lot["main_group"]:
        return []
    result = recommend(
        session,
        lot["main_group"],
        lot["start_price"],
        eshop=lot["is_eshop"],
        msp_only=lot["is_smp"],
        customer_inn=lot["customer_inn"] or None,
        extra_codes=list(lot["groups"]),
        lot_date=lot["publish_date"],
    )
    return result["items"]


def run_compute(dataset: str) -> None:
    try:
        with database.session() as session:
            lots = load_lots(session, dataset)
            _jobs[dataset] = {"status": "running", "done": 0, "total": len(lots)}
            missing_names: list[str] = []
            for index, lot in enumerate(lots, start=1):
                items = compute_lot(session, lot)
                session.execute(upsert_stmt(lot["lot_id"], items))
                session.commit()
                missing_names += [item["inn"] for item in items[:NAMES_PER_LOT] if item["name"].startswith("Компания ИНН")]
                _jobs[dataset] = {"status": "running", "done": index, "total": len(lots)}
        _jobs[dataset] = {"status": "done", "done": len(lots), "total": len(lots)}
        if missing_names:
            enrich_names(list(dict.fromkeys(missing_names)))
    except Exception as error:
        _jobs[dataset] = {"status": "error", "message": str(error)}


def start_compute(dataset: str) -> dict:
    with _lock:
        if job_state(dataset).get("status") == "running":
            return job_state(dataset)
        _jobs[dataset] = {"status": "running", "done": 0, "total": 0}
    threading.Thread(target=run_compute, args=(dataset,), daemon=True).start()
    return job_state(dataset)


def upload_batch(name: str, files: list[tuple[str, bytes]]) -> dict:
    name = name.strip() or f"Пакет от {datetime.now():%d.%m.%Y %H:%M}"
    if name == HISTORY_DATASET:
        raise BatchError("Это имя зарезервировано для исторических данных")
    folder = Path(tempfile.mkdtemp(prefix="batch_"))
    try:
        for filename, content in files:
            (folder / Path(filename).name).write_bytes(content)
        try:
            sources = collect_sources(folder)
        except ValueError as error:
            raise BatchError(str(error).replace(str(folder), "загруженных файлах")) from error
        sources["stg_bids"] = []
        with database.session() as session:
            load_sources(session, sources, name, replace=False, with_classifier=False)
            added = session.execute(
                select(func.count()).select_from(AnnouncementModel).where(AnnouncementModel.dataset == name)
            ).scalar()
            if not added:
                session.rollback()
                raise BatchError("Все лоты из этих файлов уже загружены в другом пакете")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    start_compute(name)
    return {"name": name, "job": job_state(name)}


def delete_batch(dataset: str) -> None:
    if dataset == HISTORY_DATASET:
        raise BatchError("Исторические данные удалить нельзя")
    with database.session() as session:
        for stmt in delete_stmts(dataset):
            session.execute(stmt)
    _jobs.pop(dataset, None)


def lot_variants(lot_id: int) -> dict | None:
    with database.session() as session:
        row = session.execute(select(LotRecommendationModel.items).where(LotRecommendationModel.lot_id == lot_id)).first()
        if row is None:
            return None
        return {"items": fill_names(session, row[0])}


def export_csv(dataset: str, top: int = TOP_EXPORT) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(EXPORT_COLUMNS)
    with database.session() as session:
        for lot in load_lots(session, dataset):
            items = fill_names(session, (lot["items"] or [])[:top])
            for rank, item in enumerate(items, start=1):
                writer.writerow([
                    lot["lot_id"], lot["publish_date"].isoformat(), lot["subject"], lot["customer_inn"],
                    lot["start_price"], "ЭМ" if lot["is_eshop"] else "АИС ГЗ", lot["is_smp"],
                    rank, item["inn"], item["name"], item["novelty"], item["role"], item["score"],
                    item["part"], item["wins"], item.get("direct", 0), item["last"],
                    " | ".join(reason[1] for reason in item["why"]),
                ])
    return "﻿" + buffer.getvalue()