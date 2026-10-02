import re

import psycopg

RESULT_LIMIT = 50

_catalog: list[tuple[str, str]] | None = None


def query_stems(query: str) -> list[str]:
    return [word[: max(4, len(word) - 2)] for word in re.findall(r"\w+", query.lower()) if len(word) >= 4]

def detect_okpd(conn: psycopg.Connection, query: str) -> list[tuple[str, int]]:
    stems = query_stems(query)
    if not stems:
        return []
    conditions = " AND ".join("product_name ~* %s" for _ in stems)
    return conn.execute(
        f"""
        SELECT left(okpd_code, 5) AS okpd_group, count(*)
        FROM lots
        WHERE okpd_code IS NOT NULL AND {conditions}
        GROUP BY okpd_group
        ORDER BY count(*) DESC
        LIMIT 3
        """,
        [rf"\m{stem}" for stem in stems],
    ).fetchall()


def code_prefixes(code: str) -> set[str]:
    parts = code.split(".")
    prefixes = {parts[0]}
    for index in range(1, len(parts)):
        head = ".".join(parts[:index])
        part = parts[index]
        for length in range(1, len(part) + 1):
            prefixes.add(f"{head}.{part[:length]}")
    return prefixes


def catalog(conn: psycopg.Connection) -> list[tuple[str, str]]:
    global _catalog
    if _catalog is None:
        used = set()
        for (code,) in conn.execute("SELECT DISTINCT okpd_code FROM lots WHERE okpd_code IS NOT NULL"):
            used |= code_prefixes(code)
        rows = conn.execute("SELECT code, name FROM okpd WHERE name IS NOT NULL ORDER BY code").fetchall()
        _catalog = [(code, name) for code, name in rows if code in used]
    return _catalog


def list_categories(conn: psycopg.Connection, term: str) -> list[dict]:
    term = term.strip().lower()
    entries = catalog(conn)
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


def category_name(conn: psycopg.Connection, code: str) -> str | None:
    row = conn.execute("SELECT name FROM okpd WHERE code = %s", [code]).fetchone()
    return row[0] if row else None
