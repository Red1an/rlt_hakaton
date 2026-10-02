import threading

import httpx
from psycopg.types.json import Jsonb

from worker.dadata import DadataQuotaExceeded, DadataUnavailable, parse_party, suggest_parties

from .db import connect

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_REQUESTS = 10
PER_CATEGORY = 20
ALL_REQUESTS_PER_CATEGORY = 3
SHOWN_RESULTS = 100
REGIONS = ["78", "47"]
QUERIES = ["ООО", "Санкт-Петербург", "Ленинградская", "ИП", "АО", "проспект", "улица", "шоссе", "линия", "набережная"]

GROUPS_SQL = """
    SELECT left(okpd_code, 5)
    FROM lots
    WHERE okpd_code ~ '^\\d{2}\\.\\d{2}'
    GROUP BY 1
    ORDER BY count(*) DESC
"""

FOUND_BY_CATEGORY_SQL = """
    SELECT okpds[1], count(*) FROM suppliers WHERE source = 'dadata' GROUP BY 1
"""

KNOWN_SQL = "SELECT inn FROM suppliers WHERE inn = ANY(%s)"

INSERT_SQL = """
    INSERT INTO suppliers (
        inn, kpp, name, sum_price, is_smp, okpds, source, role, role_reason,
        ogrn, status, status_date, reg_date, okved_main, address, region_code,
        opf, is_individual, employees, dadata, enriched_at
    ) VALUES (
        %(inn)s, %(kpp)s, %(name)s, 0, false, ARRAY[%(okpd)s], 'dadata', %(role)s, %(role_reason)s,
        %(ogrn)s, %(status)s, %(status_date)s, %(reg_date)s, %(okved_main)s, %(address)s, %(region_code)s,
        %(opf)s, %(is_individual)s, %(employees)s, %(dadata)s, now()
    )
    ON CONFLICT (inn) DO NOTHING
"""

STATS_SQL = """
    SELECT
        count(*) FILTER (WHERE source = 'dadata'),
        count(*) FILTER (WHERE source = 'web'),
        count(*)
    FROM suppliers
"""

_lock = threading.Lock()
_job: dict = {"status": "idle"}


def result_of(inn: str, parsed: dict) -> dict:
    return {
        "inn": inn,
        "name": parsed["name"],
        "role": parsed["role"],
        "roleReason": parsed["role_reason"],
        "okved": parsed["okved_main"],
        "regionCode": parsed["region_code"],
        "regDate": parsed["reg_date"].isoformat() if parsed["reg_date"] else None,
        "address": parsed["address"],
    }


def discover_category(conn, client: httpx.Client, okpd: str, limit: int, max_requests: int, report) -> list[dict]:
    found: list[dict] = []
    for query in QUERIES[:max_requests]:
        if len(found) >= limit:
            break
        parties = suggest_parties(client, query, [okpd], REGIONS)
        report(1, [])
        inns = [party.get("inn") for party in parties if party.get("inn")]
        known = {row[0] for row in conn.execute(KNOWN_SQL, [inns])}
        added = []
        for party in parties:
            inn = party.get("inn")
            if not inn or inn in known or len(found) + len(added) >= limit:
                continue
            parsed = parse_party(party)
            if conn.execute(INSERT_SQL, {**parsed, "inn": inn, "okpd": okpd, "dadata": Jsonb(party)}).rowcount:
                known.add(inn)
                added.append(result_of(inn, parsed))
        conn.commit()
        found += added
        report(0, added)
    return found


def run_discovery(okpd: str | None, limit: int) -> None:
    global _job
    job = {"status": "running", "okpd": okpd, "limit": limit, "requests": 0, "found": 0, "results": []}

    def report(requests: int, added: list[dict]) -> None:
        global _job
        job["requests"] += requests
        job["found"] += len(added)
        job["results"] = (job["results"] + added)[-SHOWN_RESULTS:]
        _job = dict(job)

    try:
        with connect() as conn, httpx.Client(timeout=15) as client:
            if okpd:
                discover_category(conn, client, okpd, limit, MAX_REQUESTS, report)
            else:
                found_by_category = dict(conn.execute(FOUND_BY_CATEGORY_SQL).fetchall())
                groups = [row[0] for row in conn.execute(GROUPS_SQL)]
                job.update({"categories": len(groups), "categoriesDone": 0})
                for group in groups:
                    job["current"] = group
                    need = PER_CATEGORY - found_by_category.get(group, 0)
                    if need > 0:
                        discover_category(conn, client, group, need, ALL_REQUESTS_PER_CATEGORY, report)
                    job["categoriesDone"] += 1
                    _job = dict(job)
        job["status"] = "done"
    except (DadataQuotaExceeded, DadataUnavailable) as error:
        job.update({"status": "stopped", "message": str(error)})
    except Exception as error:
        job.update({"status": "error", "message": str(error)})
    job.pop("current", None)
    _job = dict(job)


def start_enrichment(okpd: str | None, limit: int) -> dict:
    global _job
    limit = PER_CATEGORY if okpd is None else max(1, min(limit, MAX_LIMIT))
    with _lock:
        if _job.get("status") == "running":
            return enrichment_state()
        _job = {"status": "running", "okpd": okpd, "limit": limit, "requests": 0, "found": 0, "results": []}
    threading.Thread(target=run_discovery, args=(okpd, limit), daemon=True).start()
    return enrichment_state()


def enrichment_state() -> dict:
    with connect() as conn:
        found, web, total = conn.execute(STATS_SQL).fetchone()
    return {
        "job": _job,
        "maxLimit": MAX_LIMIT,
        "perCategory": PER_CATEGORY,
        "suppliers": {"total": total, "found": found, "web": web},
    }
