import argparse

import lightgbm as lgb
import pandas as pd

from ml.data import CACHE_DIR, load_all
from ml.features import FEATURES, build_examples
from ml.text import lot_typicality
from ml.train import TEST_CUTOFF, TEST_UNTIL, TRAIN_CUTOFF, TRAIN_UNTIL, fit_ranker
from api.db import connect

EVAL_MODEL_PATH = CACHE_DIR / "eval_model.txt"
SHOWN = 5
TOP_K = 10


def eval_model(
    lots: pd.DataFrame,
    bids: pd.DataFrame,
    suppliers: pd.DataFrame,
    max_lots: int,
    typicality: pd.Series,
) -> lgb.Booster:
    if not EVAL_MODEL_PATH.exists():
        train, _ = build_examples(lots, bids, suppliers, TRAIN_CUTOFF, TRAIN_UNTIL, max_lots, seed=1, typicality=typicality)
        fit_ranker(train).booster_.save_model(EVAL_MODEL_PATH)
    return lgb.Booster(model_file=str(EVAL_MODEL_PATH))


def lookup(lot_ids: list[int], inns: list[str]) -> tuple[dict[int, str], dict[str, str]]:
    with connect() as conn:
        subjects = dict(conn.execute("SELECT lot_id, subject FROM announcements WHERE lot_id = ANY(%s)", [lot_ids]))
        names = dict(conn.execute("SELECT inn, coalesce(name, 'ИНН ' || inn) FROM suppliers WHERE inn = ANY(%s)", [inns]))
    return subjects, names


def main() -> None:
    parser = argparse.ArgumentParser(description="Разбор реальных закупок: кого предложила модель и кто участвовал")
    parser.add_argument("--cases", type=int, default=12)
    parser.add_argument("--max-lots", type=int, default=30000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    lots, bids, suppliers = load_all()
    typicality = lot_typicality(lots)
    model = eval_model(lots, bids, suppliers, args.max_lots, typicality)
    test, truth = build_examples(lots, bids, suppliers, TEST_CUTOFF, TEST_UNTIL, args.max_lots, seed=2, typicality=typicality)
    test["score"] = model.predict(test[FEATURES])
    test = test.sort_values(["lot_id", "score"], ascending=[True, False])
    test["position"] = test.groupby("lot_id").cumcount() + 1

    eligible = truth[(truth["participants"] >= 2) & (truth["winners"] == 1)].index
    chosen = pd.Series(eligible).sample(args.cases, random_state=args.seed).tolist()
    actual = bids[bids["lot_id"].isin(chosen)]
    cases = test[test["lot_id"].isin(chosen)]
    subjects, names = lookup(chosen, list(set(cases[cases["position"] <= SHOWN]["supplier_inn"]) | set(actual["supplier_inn"])))

    hits = 0
    for lot_id in chosen:
        lot_rows = cases[cases["lot_id"] == lot_id]
        lot = lots[lots["lot_id"] == lot_id].iloc[0]
        participants = actual[actual["lot_id"] == lot_id]
        winner = participants[participants["is_winner"]]["supplier_inn"].iloc[0]
        winner_rows = lot_rows[lot_rows["supplier_inn"] == winner]
        winner_position = int(winner_rows["position"].iloc[0]) if len(winner_rows) else None
        found = lot_rows[(lot_rows["position"] <= TOP_K) & (lot_rows["participated"] == 1)]
        hits += winner_position is not None and winner_position <= TOP_K

        platform = "ЭМ" if lot["is_eshop"] else "АИС ГЗ"
        print(f"\n■ {subjects.get(lot_id, '')[:90]}")
        print(f"  ОКПД2 {lot['okpd_group']} · НМЦК {lot['start_price']:,.0f} ₽ · {platform} · участников {len(participants)}".replace(",", " "))
        for _, row in lot_rows[lot_rows["position"] <= SHOWN].iterrows():
            mark = "🏆 победил" if row["won"] else ("✅ участвовал" if row["participated"] else "")
            print(f"   {row['position']:>2}. {names.get(row['supplier_inn'], row['supplier_inn'])[:40]:40} {mark}")
        verdict = f"на {winner_position}-м месте" if winner_position else "не было среди кандидатов"
        print(f"  Победитель {names.get(winner, winner)[:40]}: {verdict}")
        print(f"  Реальных участников в нашем топ-{TOP_K}: {len(found)} из {len(participants)}")

    print(f"\nИтого: победитель в топ-{TOP_K} в {hits} из {len(chosen)} закупок")


if __name__ == "__main__":
    main()
