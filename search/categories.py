import re

import psycopg


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
