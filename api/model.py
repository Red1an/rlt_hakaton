import json
import math
import threading
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    distinct,
    func,
    insert,
    select,
)
from sqlalchemy.schema import CreateTable

from database import AnnouncementModel, BidModel, LotModel, database

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml" / "model"
LOT_FEATURES = {"lot_log_price", "lot_is_eshop", "lot_is_smp"}

_lock = threading.Lock()
_booster: lgb.Booster | None = None
_features: list[str] = []
_profiles: dict[str, tuple[int, int, bool]] | None = None
_class_bids: dict[tuple[str, str], int] | None = None


def lot_groups() -> Table:
    return Table(
        "lot_groups",
        MetaData(),
        Column("lot_id", Integer),
        Column("okpd_group", String),
        prefixes=["TEMPORARY"],
        postgresql_on_commit="DROP",
    )


def fill_lot_groups(session, groups: Table) -> None:
    session.execute(CreateTable(groups))
    session.execute(
        insert(groups).from_select(
            ["lot_id", "okpd_group"],
            select(
                LotModel.lot_id,
                func.mode().within_group(func.left(LotModel.okpd_code, 5)).label("okpd_group"),
            )
            .where(LotModel.okpd_code.regexp_match(r"^\d{2}\.\d{2}"))
            .group_by(LotModel.lot_id),
        )
    )


def profile_stmts(groups: Table) -> tuple:
    okpd_group = groups.c.okpd_group
    totals = (
        select(
            BidModel.supplier_inn,
            func.count().label("bids"),
            func.count(distinct(okpd_group)).label("groups"),
            func.bool_or(AnnouncementModel.is_smp).label("is_msp"),
        )
        .select_from(BidModel)
        .join(AnnouncementModel, AnnouncementModel.lot_id == BidModel.lot_id)
        .join(groups, groups.c.lot_id == BidModel.lot_id)
        .group_by(BidModel.supplier_inn)
    )
    classes = (
        select(
            BidModel.supplier_inn,
            func.left(okpd_group, 2).label("class"),
            func.count().label("bids"),
        )
        .select_from(BidModel)
        .join(groups, groups.c.lot_id == BidModel.lot_id)
        .group_by(BidModel.supplier_inn, func.left(okpd_group, 2))
    )
    return totals, classes


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
            with database.session() as session:
                groups = lot_groups()
                fill_lot_groups(session, groups)
                totals, classes = profile_stmts(groups)
                _profiles = {inn: (bids, groups_cnt, msp) for inn, bids, groups_cnt, msp in session.execute(totals)}
                _class_bids = {(inn, cls): bids for inn, cls, bids in session.execute(classes)}
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