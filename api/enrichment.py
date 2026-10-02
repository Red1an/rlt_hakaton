import threading

import httpx
from psycopg.types.json import Jsonb

from worker.dadata import DadataQuotaExceeded, DadataUnavailable, fetch_party, parse_party

from .db import connect

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
FRESH_DAYS = 7
CANDIDATE_CAP = 5000
TOP_RECOMMENDED = 10
CLOSED_STATUSES = ("LIQUIDATED", "BANKRUPT")

RECOMMENDED_SQL = """
    SELECT DISTINCT item ->> 'inn'
    FROM lot_recommendations r,
         jsonb_array_elements(r.items) WITH ORDINALITY AS t(item, position)
    WHERE t.position <= %(top)s
"""

CATEGORY_SQL = """
    SELECT b.supplier_inn
    FROM bids b
    JOIN (SELECT DISTINCT lot_id FROM lots WHERE okpd_code LIKE %(prefix)s) l ON l.lot_id = b.lot_id
    GROUP BY b.supplier_inn
    ORDER BY count(*) FILTER (WHERE b.is_winner) DESC, count(*) DESC
    LIMIT %(cap)s
"""

WEB_SQL = """
    SELECT inn FROM suppliers
    WHERE source = 'web'
      AND (%(okpd)s::text IS NULL OR EXISTS (
          SELECT 1 FROM unnest(okpds) code WHERE code LIKE %(prefix)s OR %(okpd)s LIKE code || '%%'
      ))
"""

ACTIVE_SQL = """
    SELECT supplier_inn FROM bids
    GROUP BY supplier_inn
    ORDER BY count(*) DESC
    LIMIT %(cap)s
"""

FRESH_SQL = """
    SELECT inn FROM suppliers
    WHERE inn = ANY(%(inns)s) AND enriched_at > now() - make_interval(days => %(days)s)
"""

CURRENT_SQL = "SELECT source, role, role_reason FROM suppliers WHERE inn = %s"

UPDATE_SQL = """
    UPDATE suppliers SET
        name = coalesce(%(name)s, name),
        kpp = coalesce(%(kpp)s, kpp),
        ogrn = %(ogrn)s,
        status = %(status)s,
        status_date = %(status_date)s,
        reg_date = %(reg_date)s,
        okved_main = %(okved_main)s,
        address = %(address)s,
        region_code = %(region_code)s,
        opf = %(opf)s,
        is_individual = %(is_individual)s,
        employees = %(employees)s,
        role = coalesce(%(role)s, role),
        role_reason = coalesce(%(role_reason)s, role_reason),
        dadata = %(dadata)s,
        enriched_at = now()
    WHERE inn = %(inn)s
"""

NOT_FOUND_SQL = "UPDATE suppliers SET status = 'NOT_FOUND', enriched_at = now() WHERE inn = %s"

STATS_SQL = """
    SELECT
        count(*) FILTER (WHERE enriched_at IS NOT NULL),
        count(*) FILTER (WHERE status IN ('LIQUIDATED', 'BANKRUPT')),
        count(*) FILTER (WHERE status IN ('LIQUIDATING', 'REORGANIZING')),
        count(*)
    FROM suppliers
"""

_lock = threading.Lock()
_job: dict = {"status": "idle"}


def select_inns(conn, okpd: str | None, limit: int) -> list[str]:
    params = {"okpd": okpd, "prefix": f"{okpd}%" if okpd else None, "cap": CANDIDATE_CAP, "top": TOP_RECOMMENDED}
    queries = [CATEGORY_SQL, WEB_SQL] if okpd else [RECOMMENDED_SQL, WEB_SQL, ACTIVE_SQL]
    ordered = []
    for sql in queries:
        ordered += [row[0] for row in conn.execute(sql, params) if row[0]]
    ordered = list(dict.fromkeys(ordered))
    fresh = {row[0] for row in conn.execute(FRESH_SQL, {"inns": ordered, "days": FRESH_DAYS})}
    return [inn for inn in ordered if inn not in fresh][:limit]


def merged_role(parsed: dict, current: tuple | None) -> None:
    if current is None or parsed["role"] is None:
        return
    source, role, reason = current
    if source == "web" and reason and role and role != parsed["role"]:
        parsed["role_reason"] = f"{parsed['role_reason']}; на сайте: {reason}"


def enrich_one(conn, client: httpx.Client, inn: str) -> dict:
    data = fetch_party(client, inn)
    if data is None:
        conn.execute(NOT_FOUND_SQL, [inn])
        return {"inn": inn, "name": None, "status": "NOT_FOUND"}
    parsed = parse_party(data)
    merged_role(parsed, conn.execute(CURRENT_SQL, [inn]).fetchone())
    conn.execute(UPDATE_SQL, {**parsed, "inn": inn, "dadata": Jsonb(data)})
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
        with connect() as conn, httpx.Client(timeout=15) as client:
            inns = select_inns(conn, okpd, limit)
            _job = {"status": "running", "okpd": okpd, "total": len(inns), **counters}
            for inn in inns:
                try:
                    result = enrich_one(conn, client, inn)
                except DadataUnavailable as error:
                    counters["errors"] += 1
                    result = {"inn": inn, "name": None, "status": "ERROR", "message": str(error)}
                conn.commit()
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
    with connect() as conn:
        enriched, closed, warning, total = conn.execute(STATS_SQL).fetchone()
    return {
        "job": _job,
        "maxLimit": MAX_LIMIT,
        "suppliers": {"total": total, "enriched": enriched, "closed": closed, "warning": warning},
    }
