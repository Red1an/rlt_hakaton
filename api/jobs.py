import json
import re
import threading

import httpx
import psycopg

from .db import connect
from worker.discover import discover
from worker.egrul import egrul
from worker.utils import HEADERS

MAX_SITES = 20

_names_lock = threading.Lock()


def enrich_names(inns: list[str]) -> None:
    with _names_lock, connect() as conn, httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for inn in inns:
            record = egrul(client, inn)
            if record and record.get("name"):
                conn.execute(
                    "UPDATE suppliers SET name = %s WHERE inn = %s AND name IS NULL",
                    [record["name"], inn],
                )
                conn.commit()


def search_phrase(category_name: str) -> str:
    phrase = re.split(r",|\(| кроме ", category_name)[0].strip()
    return " ".join(phrase.split()[:6])


def find_new_suppliers(conn: psycopg.Connection, okpd: str, category_name: str) -> int:
    known_inns = {row[0] for row in conn.execute("SELECT inn FROM suppliers")}
    companies = discover(search_phrase(category_name), MAX_SITES, known_inns, refresh=True)
    for company in companies:
        conn.execute(
            """
            INSERT INTO suppliers (
                inn, kpp, name, is_smp, okpds, source, site, role,
                role_reason, contacts
            ) VALUES (
                %(inn)s, %(kpp)s, %(name)s, false, ARRAY[%(okpd)s], 'web',
                %(site)s, %(role)s, %(role_reason)s, %(contacts)s
            )
            ON CONFLICT (inn) DO UPDATE SET
                kpp = COALESCE(suppliers.kpp, EXCLUDED.kpp),
                name = COALESCE(suppliers.name, EXCLUDED.name),
                okpds = ARRAY(
                    SELECT DISTINCT value
                    FROM unnest(suppliers.okpds || EXCLUDED.okpds) AS value
                ),
                source = 'web',
                site = COALESCE(suppliers.site, EXCLUDED.site),
                role = COALESCE(suppliers.role, EXCLUDED.role),
                role_reason = COALESCE(suppliers.role_reason, EXCLUDED.role_reason),
                contacts = COALESCE(suppliers.contacts, EXCLUDED.contacts)
            """,
            {
                **company,
                "okpd": okpd,
                "contacts": json.dumps(company.get("contacts", {}), ensure_ascii=False),
            },
        )
    conn.commit()
    return len(companies)
