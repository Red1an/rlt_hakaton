import csv
import io
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from parser.load import HISTORY_DATASET, collect_sources, load_sources

from .db import connect
from .jobs import enrich_names
from .recommend import fill_names, needs_check, recommend

TOP_PREVIEW = 3
TOP_EXPORT = 10
NAMES_PER_LOT = 10
BATCH_NAMES_LIMIT = 300
COMPUTE_WORKERS = 4

BATCHES_SQL = """
    SELECT
        a.dataset,
        count(*)                AS lots,
        count(r.lot_id)         AS computed,
        min(a.publish_date)     AS date_from,
        max(a.publish_date)     AS date_to,
        max(r.computed_at)      AS computed_at
    FROM announcements a
    LEFT JOIN lot_recommendations r ON r.lot_id = a.lot_id
    WHERE a.dataset <> %(history)s
    GROUP BY a.dataset
    ORDER BY max(a.publish_date) DESC, a.dataset
"""

LOTS_SQL = """
    SELECT
        a.lot_id,
        a.publish_date,
        a.start_price,
        a.subject,
        a.is_smp,
        a.customer_inn,
        a.is_eshop_or_aisgz,
        coalesce(g.groups, ARRAY[]::text[]) AS groups,
        g.main_group,
        r.items,
        r.computed_at
    FROM announcements a
    LEFT JOIN (
        SELECT
            lot_id,
            array_agg(DISTINCT left(okpd_code, 5)) AS groups,
            mode() WITHIN GROUP (ORDER BY left(okpd_code, 5)) AS main_group
        FROM lots
        WHERE okpd_code ~ '^\\d{2}\\.\\d{2}'
          AND lot_id IN (
              SELECT lot_id FROM announcements
              WHERE (dataset = %(dataset)s AND %(lot_id)s::bigint IS NULL) OR lot_id = %(lot_id)s
          )
        GROUP BY lot_id
    ) g ON g.lot_id = a.lot_id
    LEFT JOIN lot_recommendations r ON r.lot_id = a.lot_id
    WHERE (a.dataset = %(dataset)s AND %(lot_id)s::bigint IS NULL) OR a.lot_id = %(lot_id)s
    ORDER BY a.publish_date, a.lot_id
"""

UPSERT_SQL = """
    INSERT INTO lot_recommendations (lot_id, items, computed_at)
    VALUES (%s, %s, now())
    ON CONFLICT (lot_id) DO UPDATE SET items = EXCLUDED.items, computed_at = EXCLUDED.computed_at
"""

DELETE_SQL = [
    "DELETE FROM lots WHERE lot_id IN (SELECT lot_id FROM announcements WHERE dataset = %(dataset)s)",
    "DELETE FROM announcements WHERE dataset = %(dataset)s",
]

EXPORT_COLUMNS = [
    "lot_id", "publish_date", "subject", "customer_inn", "start_price", "platform", "only_msp",
    "rank", "supplier_inn", "supplier_name", "novelty", "role", "score", "score_kind",
    "competitive_bids", "competitive_wins", "direct_contracts", "last_bid", "reasons",
]

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


class BatchError(ValueError):
    pass


def job_state(dataset: str) -> dict:
    return _jobs.get(dataset, {"status": "idle"})


def list_batches() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(BATCHES_SQL, {"history": HISTORY_DATASET}).fetchall()
    return [
        {
            "name": name,
            "lots": lots,
            "computed": computed,
            "dateFrom": date_from.isoformat() if date_from else None,
            "dateTo": date_to.isoformat() if date_to else None,
            "computedAt": computed_at.isoformat() if computed_at else None,
            "job": job_state(name),
        }
        for name, lots, computed, date_from, date_to, computed_at in rows
    ]


def load_lots(conn, dataset: str | None, lot_id: int | None = None) -> list[dict]:
    columns = ["lot_id", "publish_date", "start_price", "subject", "is_smp", "customer_inn",
               "is_eshop", "groups", "main_group", "items", "computed_at"]
    rows = conn.execute(LOTS_SQL, {"dataset": dataset, "lot_id": lot_id})
    return [dict(zip(columns, row)) for row in rows]


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
            {
                "inn": item["inn"],
                "name": item["name"],
                "score": item["score"],
                "scoreKind": item.get("scoreKind", "relative"),
                "novelty": item["novelty"],
            }
            for item in items[:TOP_PREVIEW]
        ],
    }


def batch_lots(dataset: str) -> list[dict]:
    with connect() as conn:
        lots = load_lots(conn, dataset)
        for lot in lots:
            if lot["items"]:
                fill_names(conn, lot["items"][:TOP_PREVIEW])
    return [lot_summary(lot) for lot in lots]


def compute_lot(conn, lot: dict) -> list[dict]:
    if not lot["main_group"]:
        return []
    result = recommend(
        conn,
        lot["main_group"],
        lot["start_price"],
        eshop=lot["is_eshop"],
        msp_only=lot["is_smp"],
        customer_inn=lot["customer_inn"] or None,
        extra_codes=list(lot["groups"]),
        lot_date=lot["publish_date"],
    )
    return result["items"]


def compute_and_store(lot: dict) -> list[str]:
    with connect() as conn:
        items = compute_lot(conn, lot)
        conn.execute(UPSERT_SQL, [lot["lot_id"], Jsonb(items)])
        conn.commit()
    return [item["inn"] for item in items[:NAMES_PER_LOT] if needs_check(item)]


def run_compute(dataset: str, only_missing: bool) -> None:
    try:
        with connect() as conn:
            lots = load_lots(conn, dataset)
        if only_missing:
            lots = [lot for lot in lots if lot["items"] is None]
        _jobs[dataset] = {"status": "running", "done": 0, "total": len(lots)}
        missing_names: list[str] = []
        with ThreadPoolExecutor(COMPUTE_WORKERS) as pool:
            for index, inns in enumerate(pool.map(compute_and_store, lots), start=1):
                missing_names += inns
                _jobs[dataset] = {"status": "running", "done": index, "total": len(lots)}
        _jobs[dataset] = {"status": "done", "done": len(lots), "total": len(lots)}
        if missing_names:
            enrich_names(list(dict.fromkeys(missing_names)), BATCH_NAMES_LIMIT)
    except Exception as error:
        _jobs[dataset] = {"status": "error", "message": str(error)}


def start_compute(dataset: str, only_missing: bool = False) -> dict:
    with _lock:
        if job_state(dataset).get("status") == "running":
            return job_state(dataset)
        _jobs[dataset] = {"status": "running", "done": 0, "total": 0}
    threading.Thread(target=run_compute, args=(dataset, only_missing), daemon=True).start()
    return job_state(dataset)


def compute_single(lot_id: int) -> dict | None:
    with connect() as conn:
        lots = load_lots(conn, None, lot_id)
    if not lots:
        return None
    missing_names = compute_and_store(lots[0])
    if missing_names:
        threading.Thread(target=enrich_names, args=(missing_names,), daemon=True).start()
    with connect() as conn:
        lot = load_lots(conn, None, lot_id)[0]
        fill_names(conn, (lot["items"] or [])[:TOP_PREVIEW])
    return lot_summary(lot)


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
        with connect() as conn:
            load_sources(conn, sources, name, replace=False, with_classifier=False)
            added = conn.execute("SELECT count(*) FROM announcements WHERE dataset = %s", [name]).fetchone()[0]
            if not added:
                conn.rollback()
                raise BatchError("Все лоты из этих файлов уже загружены в другом пакете")
            conn.commit()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return {"name": name, "lots": added, "job": job_state(name)}


def delete_batch(dataset: str) -> None:
    if dataset == HISTORY_DATASET:
        raise BatchError("Исторические данные удалить нельзя")
    with connect() as conn:
        for sql in DELETE_SQL:
            conn.execute(sql, {"dataset": dataset})
        conn.commit()
    _jobs.pop(dataset, None)


def lot_variants(lot_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT items FROM lot_recommendations WHERE lot_id = %s", [lot_id]).fetchone()
        if row is None:
            return None
        return {"items": fill_names(conn, row[0])}


def export_csv(dataset: str, top: int = TOP_EXPORT) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(EXPORT_COLUMNS)
    with connect() as conn:
        for lot in load_lots(conn, dataset):
            items = fill_names(conn, (lot["items"] or [])[:top])
            for rank, item in enumerate(items, start=1):
                writer.writerow([
                    lot["lot_id"], lot["publish_date"].isoformat(), lot["subject"], lot["customer_inn"],
                    lot["start_price"], "ЭМ" if lot["is_eshop"] else "АИС ГЗ", lot["is_smp"],
                    rank, item["inn"], item["name"], item["novelty"], item["role"],
                    "" if item["novelty"] == "new" else item["score"], item.get("scoreKind", "relative"),
                    item["part"], item["wins"], item.get("direct", 0), item["last"],
                    " | ".join(reason[1] for reason in item["why"]),
                ])
    return "﻿" + buffer.getvalue()
