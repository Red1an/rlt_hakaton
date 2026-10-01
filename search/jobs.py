import re
import threading

import httpx
import psycopg

from search.db import connect
from worker.discover import HEADERS, EgrulUnavailable, discover, egrul_lookup, save

MAX_SITES = 20

_names_lock = threading.Lock()


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


def search_phrase(category_name: str) -> str:
    phrase = re.split(r",|\(| кроме ", category_name)[0].strip()
    return " ".join(phrase.split()[:6])


def find_new_suppliers(conn: psycopg.Connection, okpd: str, category_name: str) -> int:
    known_inns = {row[0] for row in conn.execute("SELECT inn FROM suppliers")}
    companies = discover(search_phrase(category_name), MAX_SITES, known_inns, refresh=True)
    save(conn, companies, okpd)
    return len(companies)
