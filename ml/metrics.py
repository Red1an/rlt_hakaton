import pandas as pd

TOP_K = 10


def ranking_metrics(rows: pd.DataFrame, score: pd.Series, truth: pd.DataFrame, k: int = TOP_K) -> dict[str, float]:
    ranked = rows.assign(score=score.values).sort_values(["lot_id", "score"], ascending=[True, False])
    ranked["position"] = ranked.groupby("lot_id").cumcount() + 1
    top = ranked[ranked["position"] <= k]

    found = top.groupby("lot_id")["participated"].sum().reindex(truth.index, fill_value=0)
    winners_top = top.groupby("lot_id")["won"].max().reindex(truth.index, fill_value=0)
    winner_position = ranked[ranked["won"] == 1].groupby("lot_id")["position"].min().reindex(truth.index)
    with_winner = truth["winners"] > 0

    return {
        "winner_in_top": float(winners_top[with_winner].mean()),
        "participants_found": float((found / truth["participants"]).mean()),
        "winner_mrr": float((1 / winner_position[with_winner]).fillna(0).mean()),
        "winner_median_position": float(winner_position[with_winner].median()),
        "winner_in_candidates": float(winner_position[with_winner].notna().mean()),
    }
