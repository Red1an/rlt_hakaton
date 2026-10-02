import re

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from database import LotModel, OKPDModel

RESULT_LIMIT = 50

_catalog: list[tuple[str, str]] | None = None


def query_stems(query: str) -> list[str]:
    return [word[: max(4, len(word) - 2)] for word in re.findall(r"\w+", query.lower()) if len(word) >= 4]


def detect_okpd(session: Session, query: str) -> list[tuple[str, int]]:
    stems = query_stems(query)
    if not stems:
        return []
    matches = and_(*(LotModel.product_name.regexp_match(rf"\m{stem}", flags="i") for stem in stems))
    group = func.left(LotModel.okpd_code, 5).label("okpd_group")
    return session.execute(
        select(group, func.count())
        .where(LotModel.okpd_code.is_not(None), matches)
        .group_by(group)
        .order_by(func.count().desc())
        .limit(3)
    ).all()


def code_prefixes(code: str) -> set[str]:
    parts = code.split(".")
    prefixes = {parts[0]}
    for index in range(1, len(parts)):
        head = ".".join(parts[:index])
        part = parts[index]
        for length in range(1, len(part) + 1):
            prefixes.add(f"{head}.{part[:length]}")
    return prefixes


def catalog(session: Session) -> list[tuple[str, str]]:
    global _catalog
    if _catalog is None:
        used = set()
        for (code,) in session.execute(select(distinct(LotModel.okpd_code)).where(LotModel.okpd_code.is_not(None))):
            used |= code_prefixes(code)
        rows = session.execute(
            select(OKPDModel.code, OKPDModel.name).where(OKPDModel.name.is_not(None)).order_by(OKPDModel.code)
        ).all()
        _catalog = [(code, name) for code, name in rows if code in used]
    return _catalog


def list_categories(session: Session, term: str) -> list[dict]:
    term = term.strip().lower()
    entries = catalog(session)
    if not term:
        found = [entry for entry in entries if "." not in entry[0]]
    else:
        by_code = [entry for entry in entries if entry[0].startswith(term)]
        by_name = sorted(
            (entry for entry in entries if term in entry[1].lower() and not entry[0].startswith(term)),
            key=lambda entry: len(entry[0]),
        )
        found = by_code + by_name
    return [{"code": code, "name": name} for code, name in found[:RESULT_LIMIT]]


def category_name(session: Session, code: str) -> str | None:
    return session.execute(select(OKPDModel.name).where(OKPDModel.code == code)).scalar()