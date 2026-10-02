import json
from pathlib import Path

import psycopg

CLASSIFIER_PATH = Path(__file__).resolve().parent / "data" / "okpd2.json"


def load_classifier(conn: psycopg.Connection) -> int:
    rows = json.loads(CLASSIFIER_PATH.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO okpd (code, name) VALUES (%s, %s) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name",
            rows,
        )
    return len(rows)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from api.db import connect

    with connect() as connection:
        print(f"Справочник ОКПД2: {load_classifier(connection)} кодов")
        connection.commit()
