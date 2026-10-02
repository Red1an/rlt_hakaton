import json
import re
import threading

import httpx
from sqlalchemy import column, distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database import SuppliersModel, database
from worker.discover import discover
from worker.egrul import egrul
from worker.utils import HEADERS

MAX_SITES = 20

_names_lock = threading.Lock()


def enrich_names(inns: list[str]) -> None:
    with _names_lock, database.session() as session, httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
        for inn in inns:
            record = egrul(client, inn)
            if record and record.get("name"):
                session.execute(
                    update(SuppliersModel)
                    .where(SuppliersModel.inn == inn, SuppliersModel.name.is_(None))
                    .values(name=record["name"])
                )
                session.commit()


def search_phrase(category_name: str) -> str:
    phrase = re.split(r",|\(| кроме ", category_name)[0].strip()
    return " ".join(phrase.split()[:6])


def supplier_stmt(okpd: str, company: dict):
    stmt = pg_insert(SuppliersModel).values(
        inn=company["inn"],
        kpp=company["kpp"],
        name=company["name"],
        is_smp=False,
        okpds=[okpd],
        source="web",
        site=company["site"],
        role=company["role"],
        role_reason=company["role_reason"],
        contacts=json.dumps(company.get("contacts", {}), ensure_ascii=False),
    )
    merged_okpds = (
        select(func.array_agg(distinct(column("value"))))
        .select_from(func.unnest(SuppliersModel.okpds + stmt.excluded.okpds).table_valued("value"))
        .scalar_subquery()
    )
    return stmt.on_conflict_do_update(
        index_elements=[SuppliersModel.inn],
        set_={
            "kpp": func.coalesce(SuppliersModel.kpp, stmt.excluded.kpp),
            "name": func.coalesce(SuppliersModel.name, stmt.excluded.name),
            "okpds": merged_okpds,
            "source": "web",
            "site": func.coalesce(SuppliersModel.site, stmt.excluded.site),
            "role": func.coalesce(SuppliersModel.role, stmt.excluded.role),
            "role_reason": func.coalesce(SuppliersModel.role_reason, stmt.excluded.role_reason),
            "contacts": func.coalesce(SuppliersModel.contacts, stmt.excluded.contacts),
        },
    )


def find_new_suppliers(session: Session, okpd: str, category_name: str) -> int:
    known_inns = set(session.execute(select(SuppliersModel.inn)).scalars())
    companies = discover(search_phrase(category_name), MAX_SITES, known_inns, refresh=True)
    for company in companies:
        session.execute(supplier_stmt(okpd, company))
    session.commit()
    return len(companies)