import numpy as np
import pandas as pd

TOP_BY_WINS = 50
TOP_BY_RECENCY = 50
LOCAL_REGIONS = {"78", "47"}

FEATURES = [
    "part",
    "wins",
    "win_share",
    "comp_part",
    "comp_wins",
    "comp_win_share",
    "direct_cnt",
    "days_since_last",
    "platform_share",
    "price_fit",
    "is_local",
    "customer_bids",
    "customer_group_bids",
    "total_bids",
    "groups_cnt",
    "class_bids",
    "is_msp",
    "lot_log_price",
    "lot_is_eshop",
    "lot_is_smp",
]


def supplier_regions(suppliers: pd.DataFrame) -> pd.Series:
    kpp = suppliers["kpp"].fillna("")
    valid = (kpp.str.len() == 9) & ~kpp.str.startswith("99") & ~kpp.str.startswith("00")
    region = np.where(valid, kpp.str[:2], suppliers["inn"].str[:2])
    return pd.Series(region, index=suppliers["inn"])


def history_stats(history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    participants = history.groupby("lot_id")["supplier_inn"].transform("size")
    history = history.assign(
        competitive=(participants >= 2).astype(int),
        comp_win=((participants >= 2) & history["is_winner"]).astype(int),
        direct=(participants == 1).astype(int),
    )
    by_group = history.groupby(["supplier_inn", "okpd_group"]).agg(
        part=("lot_id", "size"),
        wins=("is_winner", "sum"),
        comp_part=("competitive", "sum"),
        comp_wins=("comp_win", "sum"),
        direct_cnt=("direct", "sum"),
        last_date=("publish_date", "max"),
        eshop_bids=("is_eshop", "sum"),
        typical_price=("start_price", "median"),
    ).reset_index()

    history = history.assign(okpd_class=history["okpd_group"].str[:2])
    by_supplier = history.groupby("supplier_inn").agg(
        total_bids=("lot_id", "size"),
        groups_cnt=("okpd_group", "nunique"),
        is_msp=("is_smp", "max"),
    ).reset_index()
    by_class = history.groupby(["supplier_inn", "okpd_class"]).size().rename("class_bids").reset_index()
    by_customer = history.groupby(["supplier_inn", "customer_inn"]).size().rename("customer_bids").reset_index()
    by_customer_group = (
        history.groupby(["supplier_inn", "customer_inn", "okpd_group"]).size().rename("customer_group_bids").reset_index()
    )
    return {
        "group": by_group,
        "supplier": by_supplier,
        "class": by_class,
        "customer": by_customer,
        "customer_group": by_customer_group,
    }


def group_candidates(by_group: pd.DataFrame) -> pd.DataFrame:
    by_wins = by_group.sort_values(["okpd_group", "wins", "part"], ascending=[True, False, False])
    by_recency = by_group.sort_values(["okpd_group", "last_date"], ascending=[True, False])
    top = pd.concat([
        by_wins.groupby("okpd_group").head(TOP_BY_WINS),
        by_recency.groupby("okpd_group").head(TOP_BY_RECENCY),
    ])
    return top[["supplier_inn", "okpd_group"]].drop_duplicates()


def candidate_pairs(target_lots: pd.DataFrame, stats: dict[str, pd.DataFrame]) -> pd.DataFrame:
    lot_keys = target_lots[["lot_id", "okpd_group", "customer_inn"]]
    by_group = lot_keys.merge(group_candidates(stats["group"]), on="okpd_group")
    by_customer = lot_keys.merge(stats["customer_group"][["supplier_inn", "customer_inn", "okpd_group"]], on=["customer_inn", "okpd_group"])
    pairs = pd.concat([by_group[["lot_id", "supplier_inn"]], by_customer[["lot_id", "supplier_inn"]]])
    return pairs.drop_duplicates()


def build_examples(
    lots: pd.DataFrame,
    bids: pd.DataFrame,
    suppliers: pd.DataFrame,
    cutoff: str,
    until: str,
    max_lots: int | None = None,
    seed: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff_date, until_date = pd.Timestamp(cutoff), pd.Timestamp(until)
    lot_bids = bids.merge(lots, on="lot_id")
    history = lot_bids[lot_bids["publish_date"] <= cutoff_date]
    stats = history_stats(history)

    target_lots = lots[(lots["publish_date"] > cutoff_date) & (lots["publish_date"] <= until_date)]
    target_lots = target_lots[target_lots["lot_id"].isin(bids["lot_id"])]
    if max_lots and len(target_lots) > max_lots:
        target_lots = target_lots.sample(max_lots, random_state=seed)

    rows = target_lots.merge(candidate_pairs(target_lots, stats), on="lot_id")
    rows = rows.merge(stats["group"], on=["supplier_inn", "okpd_group"])
    rows = rows.merge(stats["supplier"], on="supplier_inn", how="left")
    rows = rows.assign(okpd_class=rows["okpd_group"].str[:2])
    rows = rows.merge(stats["class"], on=["supplier_inn", "okpd_class"], how="left")
    rows = rows.merge(stats["customer"], on=["supplier_inn", "customer_inn"], how="left")
    rows = rows.merge(stats["customer_group"], on=["supplier_inn", "customer_inn", "okpd_group"], how="left")

    regions = supplier_regions(suppliers)
    eshop_share = rows["eshop_bids"] / rows["part"]
    rows["win_share"] = rows["wins"] / rows["part"]
    rows["comp_win_share"] = rows["comp_wins"] / rows["comp_part"].replace(0, np.nan)
    rows["days_since_last"] = (rows["publish_date"] - rows["last_date"]).dt.days
    rows["platform_share"] = np.where(rows["is_eshop"], eshop_share, 1 - eshop_share)
    rows["price_fit"] = np.clip(1 - np.abs(np.log10(rows["start_price"].clip(lower=1) / rows["typical_price"].clip(lower=1))) / 2, 0, 1)
    rows["is_local"] = rows["supplier_inn"].map(regions).isin(LOCAL_REGIONS).astype(int)
    rows["customer_bids"] = rows["customer_bids"].fillna(0)
    rows["customer_group_bids"] = rows["customer_group_bids"].fillna(0)
    rows["class_bids"] = rows["class_bids"].fillna(0)
    rows["is_msp"] = rows["is_msp"].fillna(False).astype(int)
    rows["lot_log_price"] = np.log10(rows["start_price"].clip(lower=1))
    rows["lot_is_eshop"] = rows["is_eshop"].astype(int)
    rows["lot_is_smp"] = rows["is_smp"].astype(int)

    labels = bids[bids["lot_id"].isin(target_lots["lot_id"])]
    rows = rows.merge(
        labels.rename(columns={"is_winner": "won"}).assign(participated=1),
        on=["lot_id", "supplier_inn"],
        how="left",
    )
    rows["participated"] = rows["participated"].fillna(0).astype(int)
    rows["won"] = rows["won"].fillna(False).astype(int)

    truth = labels.groupby("lot_id").agg(participants=("supplier_inn", "size"), winners=("is_winner", "sum"))
    return rows, truth


def formula_score(rows: pd.DataFrame) -> pd.Series:
    return (
        25 * np.minimum(1.0, np.log1p(rows["part"]) / np.log1p(300))
        + 25 * (rows["wins"] + 1) / (rows["part"] + 2)
        + 20 * np.maximum(0.0, 1 - rows["days_since_last"] / 730)
        + 10 * rows["is_local"]
        + 10 * rows["platform_share"]
        + 10 * rows["price_fit"]
    )


def baseline_score(rows: pd.DataFrame) -> pd.Series:
    return rows["wins"] * 1_000_000 + rows["part"]
