import json
import math
import threading
from pathlib import Path

import lightgbm as lgb
import numpy as np

from .db import connect

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml" / "model"
LOT_FEATURES = {"lot_log_price", "lot_is_eshop", "lot_is_smp"}

PROFILE_SQL = [
    """
    CREATE TEMP TABLE lot_groups ON COMMIT DROP AS
    SELECT lot_id, mode() WITHIN GROUP (ORDER BY left(okpd_code, 5)) AS okpd_group
    FROM lots
    WHERE okpd_code ~ '^\\d{2}\\.\\d{2}'
    GROUP BY lot_id
    """,
    """
    SELECT b.supplier_inn, count(*), count(DISTINCT g.okpd_group), bool_or(a.is_smp)
    FROM bids b
    JOIN announcements a ON a.lot_id = b.lot_id
    JOIN lot_groups g ON g.lot_id = b.lot_id
    GROUP BY b.supplier_inn
    """,
    """
    SELECT b.supplier_inn, left(g.okpd_group, 2), count(*)
    FROM bids b
    JOIN lot_groups g ON g.lot_id = b.lot_id
    GROUP BY b.supplier_inn, left(g.okpd_group, 2)
    """,
]

_lock = threading.Lock()
_booster: lgb.Booster | None = None
_features: list[str] = []
_profiles: dict[str, tuple[int, int, bool]] | None = None
_class_bids: dict[tuple[str, str], int] | None = None


def model_available() -> bool:
    return (MODEL_DIR / "model.txt").exists() and (MODEL_DIR / "metrics.json").exists()


def booster() -> tuple[lgb.Booster, list[str]]:
    global _booster, _features
    with _lock:
        if _booster is None:
            _booster = lgb.Booster(model_file=str(MODEL_DIR / "model.txt"))
            _features = json.loads((MODEL_DIR / "metrics.json").read_text(encoding="utf-8"))["features"]
    return _booster, _features


def supplier_profiles() -> tuple[dict[str, tuple[int, int, bool]], dict[tuple[str, str], int]]:
    global _profiles, _class_bids
    with _lock:
        if _profiles is None:
            with connect() as conn:
                conn.execute(PROFILE_SQL[0])
                _profiles = {inn: (total, groups, msp) for inn, total, groups, msp in conn.execute(PROFILE_SQL[1])}
                _class_bids = {(inn, cls): count for inn, cls, count in conn.execute(PROFILE_SQL[2])}
    return _profiles, _class_bids


def feature_values(row: dict, lot: dict) -> dict[str, float]:
    profiles, class_bids = supplier_profiles()
    total_bids, groups_cnt, is_msp = profiles.get(row["inn"], (row["part"], 1, False))
    eshop_share = row["eshop_bids"] / row["part"]
    nmck = max(lot["nmck"], 1.0)
    return {
        "part": row["part"],
        "wins": row["wins"],
        "win_share": row["wins"] / row["part"],
        "comp_part": row["comp_part"],
        "comp_wins": row["comp_wins"],
        "comp_win_share": row["comp_wins"] / row["comp_part"] if row["comp_part"] else float("nan"),
        "direct_cnt": row["direct_cnt"],
        "days_since_last": row["days"],
        "platform_share": eshop_share if lot["eshop"] else 1 - eshop_share,
        "price_fit": min(1.0, max(0.0, 1 - abs(math.log10(nmck / max(row["typical_price"], 1.0))) / 2)),
        "is_local": int(row["is_local"]),
        "customer_bids": row["customer_bids"],
        "customer_group_bids": row["customer_group_bids"],
        "total_bids": total_bids,
        "groups_cnt": groups_cnt,
        "class_bids": class_bids.get((row["inn"], lot["okpd"][:2]), 0),
        "is_msp": int(is_msp),
        "lot_log_price": math.log10(nmck),
        "lot_is_eshop": int(lot["eshop"]),
        "lot_is_smp": int(lot["smp"]),
    }


def predict(rows: list[dict], lot: dict) -> tuple[np.ndarray, list[dict[str, float]]]:
    model, features = booster()
    values = [feature_values(row, lot) for row in rows]
    matrix = np.array([[value[name] for name in features] for value in values], dtype=float)
    scores = model.predict(matrix)
    contributions = model.predict(matrix, pred_contrib=True)[:, : len(features)]
    impacts = [
        {name: float(contribution[index]) for index, name in enumerate(features) if name not in LOT_FEATURES}
        for contribution in contributions
    ]
    return scores, impacts
