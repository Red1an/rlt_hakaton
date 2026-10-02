import re

import psycopg

RESULT_LIMIT = 50

_catalog: list[tuple[str, str, int]] | None = None


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


GROUP_PATTERN = re.compile(r"^\d{2}\.\d{2}")


def is_selectable(code: str) -> bool:
    return bool(GROUP_PATTERN.match(code))


def catalog(conn: psycopg.Connection) -> list[tuple[str, str, int]]:
    global _catalog
    if _catalog is None:
        usage: dict[str, int] = {}
        for code, count in conn.execute(
            "SELECT okpd_code, count(DISTINCT lot_id) FROM lots WHERE okpd_code IS NOT NULL GROUP BY okpd_code"
        ):
            for prefix in code_prefixes(code):
                usage[prefix] = usage.get(prefix, 0) + count
        rows = conn.execute("SELECT code, name FROM okpd WHERE name IS NOT NULL ORDER BY code").fetchall()
        _catalog = [(code, name, usage[code]) for code, name in rows if code in usage and is_selectable(code)]
    return _catalog


def list_categories(conn: psycopg.Connection, term: str) -> list[dict]:
    term = term.strip().lower()
    entries = catalog(conn)
    if not term:
        found = sorted((entry for entry in entries if len(entry[0]) == 5), key=lambda entry: -entry[2])
    else:
        by_code = sorted((entry for entry in entries if entry[0].startswith(term)), key=lambda entry: (len(entry[0]), entry[0]))
        by_name = sorted(
            (entry for entry in entries if term in entry[1].lower() and not entry[0].startswith(term)),
            key=lambda entry: (len(entry[0]), -entry[2]),
        )
        found = by_code + by_name
    return [{"code": code, "name": name} for code, name, _ in found[:RESULT_LIMIT]]


def category_name(conn: psycopg.Connection, code: str) -> str | None:
    row = conn.execute("SELECT name FROM okpd WHERE code = %s", [code]).fetchone()
    return row[0] if row else None
