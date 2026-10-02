import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func, inspect, select

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import database

from parser.okpd import load_classifier

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


OPTIONAL_TABLES = {"stg_bids"}
HISTORY_DATASET = "history"


class SourceError(ValueError):
    pass


def collect_sources(data_dir: Path) -> dict[str, list[Path]]:
    errors = []
    sources = {}
    for table, (prefix, expected_columns) in RAW_FILES.items():
        files = find_csv_files(data_dir, prefix)
        if not files and table not in OPTIONAL_TABLES:
            errors.append(f"нет файлов {prefix}*.csv")
        for path in files:
            header = read_header(path)
            if header != expected_columns:
                errors.append(f"{path.name}: колонки {header}, ожидались {expected_columns}")
        sources[table] = files
    if errors:
        raise SourceError(f"Проблемы с данными в {data_dir}:\n  " + "\n  ".join(errors))
    return sources


def run_sql_file(session, name: str) -> None:
    started = time.perf_counter()
    session.connection().exec_driver_sql((SQL_DIR / name).read_text(encoding="utf-8"))
    print(f"{name}: {time.perf_counter() - started:.1f} с")


def copy_csv(session, table: str, path: Path) -> None:
    """Потоковая загрузка CSV: SQLAlchemy держит соединение и транзакцию,
    а COPY-канал драйвера только передаёт байты файла в сервер."""
    started = time.perf_counter()
    statement = f"COPY {table} FROM STDIN (FORMAT csv, DELIMITER ';', HEADER true, ENCODING 'UTF8')"
    dbapi = session.connection().connection.driver_connection
    cursor = dbapi.cursor()
    with cursor.copy(statement) as copy, path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            copy.write(chunk)
    print(f"{table} ← {path.name}: {cursor.rowcount} строк, {time.perf_counter() - started:.1f} с")


def check_tables() -> None:
    existing = set(inspect(database.engine).get_table_names())
    missing = [table for table in REQUIRED_TABLES if table not in existing]
    if missing:
        sys.exit(f"В базе нет таблиц: {', '.join(missing)}. Сначала создайте схему из database/models.")


def load_sources(
    session,
    sources: dict[str, list[Path]],
    dataset: str,
    replace: bool,
    with_classifier: bool = True,
) -> None:
    if replace:
        run_sql_file(session, "truncate.sql")
    run_sql_file(session, "staging.sql")
    for table, files in sources.items():
        for path in files:
            copy_csv(session, table, path)
    if with_classifier:
        print(f"Справочник ОКПД2: {load_classifier(session)} кодов")
    session.execute(select(func.set_config("app.dataset", dataset, True)))
    run_sql_file(session, "load.sql")


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

    database.init()
    check_tables()
    with database.session() as session:
        load_sources(session, sources, dataset, replace)


if __name__ == "__main__":
    main()