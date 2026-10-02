import argparse
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser.okpd import load_classifier

PARSER_DIR = Path(__file__).resolve().parent
SQL_DIR = PARSER_DIR / "sql"
CHUNK_SIZE = 1 << 20

REQUIRED_TABLES = ["okpd", "announcements", "lots", "suppliers", "bids"]

RAW_FILES = {
    "stg_lots": (
        "извещениями",
        ["publish_date", "procedure_id", "lot_id", "start_price", "reqnum", "procedure_name",
         "subject", "is_smp", "customer_inn", "customer_kpp", "is_eshop_or_aisgz"],
    ),
    "stg_bids": (
        "заявками поставщиков",
        ["lot_id", "supplier_inn", "supplier_kpp", "is_winner"],
    ),
    "stg_products": (
        "товарами (ТРУ)",
        ["lot_id", "product_name", "okpd2_code"],
    ),
}


def read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig") as source:
        first_line = source.readline().strip()
    return [column.strip().strip('"').lower() for column in first_line.split(";")]


def detect_table(header: list[str]) -> str | None:
    return next((table for table, (_, columns) in RAW_FILES.items() if header == columns), None)


OPTIONAL_TABLES = {"stg_bids"}
HISTORY_DATASET = "history"


class SourceError(ValueError):
    pass


def collect_sources(data_dir: Path) -> dict[str, list[Path]]:
    errors = []
    sources: dict[str, list[Path]] = {table: [] for table in RAW_FILES}
    for path in sorted(data_dir.glob("*.csv")):
        header = read_header(path)
        table = detect_table(header)
        if table is None:
            errors.append(f"{path.name}: не похож ни на один из форматов, колонки {header}")
        else:
            sources[table].append(path)
    for table, (label, expected_columns) in RAW_FILES.items():
        if not sources[table] and table not in OPTIONAL_TABLES:
            errors.append(f"нет файла с {label}, нужны колонки {expected_columns}")
    if errors:
        raise SourceError(f"Проблемы с данными в {data_dir}:\n  " + "\n  ".join(errors))
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


def load_sources(
    conn: psycopg.Connection,
    sources: dict[str, list[Path]],
    dataset: str,
    replace: bool,
    with_classifier: bool = True,
) -> None:
    if replace:
        run_sql_file(conn, "truncate.sql")
    run_sql_file(conn, "staging.sql")
    for table, files in sources.items():
        for path in files:
            copy_csv(conn, table, path)
    if with_classifier:
        print(f"Справочник ОКПД2: {load_classifier(conn)} кодов")
    conn.execute("SELECT set_config('app.dataset', %s, true)", [dataset])
    run_sql_file(conn, "load.sql")


def main() -> None:
    load_dotenv(PARSER_DIR.parent / ".env")
    parser = argparse.ArgumentParser(description="Загрузка CSV организаторов в таблицы database/models")
    parser.add_argument("--data-dir", type=Path, default=os.getenv("DATA_DIR"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--append", action="store_true", help="дозагрузить лоты, не стирая историю")
    mode.add_argument("--replace", action="store_true", help="стереть лоты, товары и заявки и загрузить заново")
    parser.add_argument("--dataset", help="метка набора: history для истории, иначе имя пакета для подбора")
    args = parser.parse_args()

    if args.data_dir is None:
        sys.exit("Укажите папку с CSV: --data-dir или переменная DATA_DIR")
    try:
        sources = collect_sources(Path(args.data_dir))
    except SourceError as error:
        sys.exit(str(error))
    has_bids = bool(sources["stg_bids"])
    dataset = args.dataset or (HISTORY_DATASET if has_bids else Path(args.data_dir).name)
    replace = args.replace or (has_bids and not args.append)
    if not has_bids:
        print("Файлов «Поставщики» нет: лоты и товары загружаются без заявок")
    print("Режим: полная перезагрузка" if replace else "Режим: дозагрузка, история сохраняется")
    print(f"Набор: {dataset}")

    with psycopg.connect(connection_info()) as conn:
        check_tables(conn)
        load_sources(conn, sources, dataset, replace)
        conn.commit()


if __name__ == "__main__":
    main()
