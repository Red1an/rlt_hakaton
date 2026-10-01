import argparse
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PARSER_DIR = Path(__file__).resolve().parent
SQL_DIR = PARSER_DIR / "sql"
CHUNK_SIZE = 1 << 20

REQUIRED_TABLES = ["okpd", "announcements", "lots", "suppliers", "bids"]

RAW_FILES = {
    "stg_lots": (
        "Извещения",
        ["publish_date", "procedure_id", "lot_id", "start_price", "reqnum", "procedure_name",
         "subject", "is_smp", "customer_inn", "customer_kpp", "is_eshop_or_aisgz"],
    ),
    "stg_bids": (
        "Поставщики",
        ["lot_id", "supplier_inn", "supplier_kpp", "is_winner"],
    ),
    "stg_products": (
        "ТРУ",
        ["lot_id", "product_name", "okpd2_code"],
    ),
}


def find_csv_files(data_dir: Path, prefix: str) -> list[Path]:
    return sorted(p for p in data_dir.glob("*.csv") if p.name.startswith(prefix))


def read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig") as source:
        first_line = source.readline().strip()
    return [column.strip().strip('"') for column in first_line.split(";")]


def collect_sources(data_dir: Path) -> dict[str, list[Path]]:
    errors = []
    sources = {}
    for table, (prefix, expected_columns) in RAW_FILES.items():
        files = find_csv_files(data_dir, prefix)
        if not files:
            errors.append(f"нет файлов {prefix}*.csv")
        for path in files:
            header = read_header(path)
            if header != expected_columns:
                errors.append(f"{path.name}: колонки {header}, ожидались {expected_columns}")
        sources[table] = files
    if errors:
        sys.exit(f"Проблемы с данными в {data_dir}:\n  " + "\n  ".join(errors))
    return sources


def connection_info() -> str:
    return psycopg.conninfo.make_conninfo(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
    )


def run_sql_file(conn: psycopg.Connection, name: str) -> None:
    started = time.perf_counter()
    conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))
    print(f"{name}: {time.perf_counter() - started:.1f} с")


def copy_csv(conn: psycopg.Connection, table: str, path: Path) -> None:
    started = time.perf_counter()
    copy_sql = f"COPY {table} FROM STDIN (FORMAT csv, DELIMITER ';', HEADER true, ENCODING 'UTF8')"
    with conn.cursor() as cur, path.open("rb") as source:
        with cur.copy(copy_sql) as copy:
            while chunk := source.read(CHUNK_SIZE):
                copy.write(chunk)
        rows = cur.rowcount
    print(f"{table} ← {path.name}: {rows} строк, {time.perf_counter() - started:.1f} с")


def check_tables(conn: psycopg.Connection) -> None:
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    }
    missing = [table for table in REQUIRED_TABLES if table not in existing]
    if missing:
        sys.exit(f"В базе нет таблиц: {', '.join(missing)}. Сначала создайте схему из database/models.")


def main() -> None:
    load_dotenv(PARSER_DIR.parent / ".env")
    parser = argparse.ArgumentParser(description="Загрузка CSV организаторов в таблицы database/models")
    parser.add_argument("--data-dir", type=Path, default=os.getenv("DATA_DIR"))
    args = parser.parse_args()

    if args.data_dir is None:
        sys.exit("Укажите папку с CSV: --data-dir или переменная DATA_DIR")
    sources = collect_sources(Path(args.data_dir))

    with psycopg.connect(connection_info()) as conn:
        check_tables(conn)
        run_sql_file(conn, "staging.sql")
        for table, files in sources.items():
            for path in files:
                copy_csv(conn, table, path)
        run_sql_file(conn, "load.sql")
        conn.commit()


if __name__ == "__main__":
    main()
