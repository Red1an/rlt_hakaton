import threading

import httpx

from search.db import connect
from worker.discover import HEADERS, EgrulUnavailable, discover, egrul_lookup, save

MAX_SITES = 20

_names_lock = threading.Lock()
_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def enrich_names(inns: list[str]) -> None:
    with _names_lock, connect() as conn, httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for inn in inns:
            try:
                record = egrul_lookup(client, inn)
            except EgrulUnavailable:
                return
            if record and record["name"]:
                conn.execute("UPDATE suppliers SET name = %s WHERE inn = %s AND name IS NULL", [record["name"], inn])
                conn.commit()


def discovery_status(okpd: str) -> dict:
    return _jobs.get(okpd, {"status": "idle"})


def try_start_discovery(okpd: str) -> bool:
    with _jobs_lock:
        if _jobs.get(okpd, {}).get("status") == "running":
            return False
        _jobs[okpd] = {"status": "running", "checked": 0, "total": 0, "found": 0}
        return True


def run_discovery(query: str, okpd: str) -> None:
    def progress(checked: int, total: int, found: int) -> None:
        _jobs[okpd] = {"status": "running", "checked": checked, "total": total, "found": found}

    try:
        with connect() as conn:
            known_inns = {row[0] for row in conn.execute("SELECT inn FROM suppliers")}
            companies = discover(query, MAX_SITES, known_inns, refresh=True, progress=progress)
            save(conn, companies, okpd)
        _jobs[okpd] = {"status": "done", "found": len(companies)}
    except Exception as error:
        _jobs[okpd] = {"status": "error", "message": str(error)}
