import threading
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import column, distinct, exists, func, or_, select, update
from sqlalchemy.orm import Session

from database import BidModel, LotModel, LotRecommendationModel, SuppliersModel, database
from worker.dadata import DadataQuotaExceeded, DadataUnavailable, fetch_party, parse_party

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
FRESH_DAYS = 7
CANDIDATE_CAP = 5000
TOP_RECOMMENDED = 10
CLOSED_STATUSES = ("LIQUIDATED", "BANKRUPT")

_lock = threading.Lock()
_job: dict = {"status": "idle"}


def recommended_stmt(top: int = TOP_RECOMMENDED):
    items = func.jsonb_array_elements(LotRecommendationModel.items).table_valued(
        column("item", LotRecommendationModel.items.type), with_ordinality="position"
    ).render_derived()
    return (
        select(distinct(items.c.item["inn"].astext))
        .select_from(LotRecommendationModel, items)
        .where(items.c.position <= top)
    )


def category_stmt(okpd: str, cap: int = CANDIDATE_CAP):
    category_lots = select(LotModel.lot_id).where(LotModel.okpd_code.like(f"{okpd}%"))
    return (
        select(BidModel.supplier_inn)
        .select_from(BidModel)
        .join(category_lots, category_lots.c.lot_id == BidModel.lot_id)
        .group_by(BidModel.supplier_inn)
        .order_by(func.count().filter(BidModel.is_winner).desc(), func.count().desc())
        .limit(cap)
    )


def web_stmt(okpd: str | None):
    stmt = select(SuppliersModel.inn).where(SuppliersModel.source == "web")
    if okpd is None:
        return stmt
    code = func.unnest(SuppliersModel.okpds).table_valued("code").render_derived()
    return stmt.where(
        exists(
            select(1)
            .select_from(code)
            .where(or_(code.c.code.like(f"{okpd}%"), okpd.like(code.c.code + "%")))
        )
    )


def active_stmt(cap: int = CANDIDATE_CAP):
    return (
        select(BidModel.supplier_inn)
        .group_by(BidModel.supplier_inn)
        .order_by(func.count().desc())
        .limit(cap)
    )


def fresh_stmt(inns: list[str], days: int = FRESH_DAYS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return select(SuppliersModel.inn).where(
        SuppliersModel.inn.in_(inns),
        SuppliersModel.enriched_at > cutoff,
    )


def current_stmt(inn: str):
    return select(SuppliersModel.source, SuppliersModel.role, SuppliersModel.role_reason).where(SuppliersModel.inn == inn)


def update_stmt(parsed: dict, inn: str):
    return update(SuppliersModel).where(SuppliersModel.inn == inn).values(
        name=func.coalesce(parsed["name"], SuppliersModel.name),
        kpp=func.coalesce(parsed["kpp"], SuppliersModel.kpp),
        ogrn=parsed["ogrn"],
        status=parsed["status"],
        status_date=parsed["status_date"],
        reg_date=parsed["reg_date"],
        okved_main=parsed["okved_main"],
        address=parsed["address"],
        region_code=parsed["region_code"],
        opf=parsed["opf"],
        is_individual=parsed["is_individual"],
        employees=parsed["employees"],
        role=func.coalesce(parsed["role"], SuppliersModel.role),
        role_reason=func.coalesce(parsed["role_reason"], SuppliersModel.role_reason),
        dadata=parsed["dadata"],
        enriched_at=func.now(),
    )


def not_found_stmt(inn: str):
    return (
        update(SuppliersModel)
        .where(SuppliersModel.inn == inn)
        .values(status="NOT_FOUND", enriched_at=func.now())
    )


def stats_stmt():
    return select(
        func.count().filter(SuppliersModel.enriched_at.is_not(None)).label("enriched"),
        func.count().filter(SuppliersModel.status.in_(CLOSED_STATUSES)).label("closed"),
        func.count().filter(SuppliersModel.status.in_(("LIQUIDATING", "REORGANIZING"))).label("warning"),
        func.count().label("total"),
    )


def select_inns(session: Session, okpd: str | None, limit: int) -> list[str]:
    queries = [category_stmt(okpd)] if okpd else [recommended_stmt(), web_stmt(okpd), active_stmt()]
    if okpd:
        queries.append(web_stmt(okpd))
    ordered = []
    for stmt in queries:
        ordered += [inn for inn in session.execute(stmt).scalars() if inn]
    ordered = list(dict.fromkeys(ordered))
    fresh = set(session.execute(fresh_stmt(ordered)).scalars())
    return [inn for inn in ordered if inn not in fresh][:limit]


def merged_role(parsed: dict, current: tuple | None) -> None:
    if current is None or parsed["role"] is None:
        return
    source, role, reason = current
    if source == "web" and reason and role and role != parsed["role"]:
        parsed["role_reason"] = f"{parsed['role_reason']}; на сайте: {reason}"


def enrich_one(session: Session, client: httpx.Client, inn: str) -> dict:
    data = fetch_party(client, inn)
    if data is None:
        session.execute(not_found_stmt(inn))
        return {"inn": inn, "name": None, "status": "NOT_FOUND"}
    parsed = {**parse_party(data), "dadata": data}
    merged_role(parsed, session.execute(current_stmt(inn)).first())
    session.execute(update_stmt(parsed, inn))
    return {
        "inn": inn,
        "name": parsed["name"],
        "status": parsed["status"],
        "role": parsed["role"],
        "roleReason": parsed["role_reason"],
        "okved": parsed["okved_main"],
        "regionCode": parsed["region_code"],
        "regDate": parsed["reg_date"].isoformat() if parsed["reg_date"] else None,
    }


def run_enrichment(okpd: str | None, limit: int) -> None:
    global _job
    counters = {"done": 0, "closed": 0, "notFound": 0, "errors": 0}
    results: list[dict] = []
    try:
        with database.session() as session, httpx.Client(timeout=15) as client:
            inns = select_inns(session, okpd, limit)
            _job = {"status": "running", "okpd": okpd, "total": len(inns), **counters}
            for inn in inns:
                try:
                    result = enrich_one(session, client, inn)
                except DadataUnavailable as error:
                    counters["errors"] += 1
                    result = {"inn": inn, "name": None, "status": "ERROR", "message": str(error)}
                session.commit()
                results.append(result)
                counters["done"] += 1
                counters["closed"] += result["status"] in CLOSED_STATUSES
                counters["notFound"] += result["status"] == "NOT_FOUND"
                _job = {"status": "running", "okpd": okpd, "total": len(inns), **counters, "results": results}
        _job = {"status": "done", "okpd": okpd, "total": len(inns), **counters, "results": results}
    except DadataQuotaExceeded as error:
        _job = {"status": "stopped", "okpd": okpd, "message": str(error), **counters, "results": results}
    except Exception as error:
        _job = {"status": "error", "okpd": okpd, "message": str(error), **counters, "results": results}


def start_enrichment(okpd: str | None, limit: int) -> dict:
    global _job
    limit = max(1, min(limit, MAX_LIMIT))
    with _lock:
        if _job.get("status") == "running":
            return enrichment_state()
        _job = {"status": "running", "okpd": okpd, "total": 0, "done": 0}
    threading.Thread(target=run_enrichment, args=(okpd, limit), daemon=True).start()
    return enrichment_state()


def enrichment_state() -> dict:
    with database.session() as session:
        row = session.execute(stats_stmt()).one()
    return {
        "job": _job,
        "maxLimit": MAX_LIMIT,
        "suppliers": {
            "total": row.total,
            "enriched": row.enriched,
            "closed": row.closed,
            "warning": row.warning,
        },
    }