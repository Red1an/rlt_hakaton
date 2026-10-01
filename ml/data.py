from pathlib import Path

import pandas as pd

from search.db import connect

CACHE_DIR = Path(__file__).resolve().parent / ".cache"

LOTS_SQL = """
    SELECT
        a.lot_id,
        a.publish_date,
        a.start_price,
        a.is_eshop_or_aisgz AS is_eshop,
        a.is_smp,
        a.customer_inn,
        g.okpd_group
    FROM announcements a
    JOIN (
        SELECT lot_id, mode() WITHIN GROUP (ORDER BY left(okpd_code, 5)) AS okpd_group
        FROM lots
        WHERE okpd_code ~ '^\\d{2}\\.\\d{2}'
        GROUP BY lot_id
    ) g ON g.lot_id = a.lot_id
"""

BIDS_SQL = "SELECT lot_id, supplier_inn, is_winner FROM bids"

SUPPLIERS_SQL = "SELECT inn, kpp FROM suppliers WHERE source = 'dataset'"


def load(name: str, sql: str, refresh: bool = False) -> pd.DataFrame:
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists() and not refresh:
        return pd.read_pickle(path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        frame = pd.DataFrame(cur.fetchall(), columns=[column.name for column in cur.description])
    frame.to_pickle(path)
    return frame


def load_all(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lots = load("lots", LOTS_SQL, refresh)
    lots["publish_date"] = pd.to_datetime(lots["publish_date"])
    lots["start_price"] = lots["start_price"].astype(float)
    bids = load("bids", BIDS_SQL, refresh)
    suppliers = load("suppliers", SUPPLIERS_SQL, refresh)
    return lots, bids, suppliers
