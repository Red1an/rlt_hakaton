import argparse
import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from ml.data import load_all
from ml.features import FEATURES, baseline_score, build_examples, formula_score
from ml.metrics import TOP_K, ranking_metrics

MODEL_DIR = Path(__file__).resolve().parent / "model"

TRAIN_CUTOFF, TRAIN_UNTIL = "2025-06-30", "2025-09-30"
TEST_CUTOFF, TEST_UNTIL = "2025-09-30", "2025-12-31"

METRIC_LABELS = {
    "winner_in_top": f"Победитель в топ-{TOP_K}",
    "participants_found": f"Доля участников в топ-{TOP_K}",
    "winner_mrr": "MRR победителя",
    "winner_median_position": "Медианная позиция победителя",
    "winner_in_candidates": "Победитель среди кандидатов",
}

MODEL_PARAMS = {
    "objective": "lambdarank",
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "verbose": -1,
}


def fit_ranker(rows: pd.DataFrame) -> lgb.LGBMRanker:
    rows = rows.sort_values("lot_id")
    model = lgb.LGBMRanker(**MODEL_PARAMS)
    model.fit(rows[FEATURES], rows["participated"] + rows["won"], group=rows.groupby("lot_id").size().values)
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение модели ранжирования поставщиков")
    parser.add_argument("--max-lots", type=int, default=30000)
    parser.add_argument("--refresh", action="store_true", help="заново выгрузить данные из базы")
    args = parser.parse_args()

    lots, bids, suppliers = load_all(args.refresh)
    train, _ = build_examples(lots, bids, suppliers, TRAIN_CUTOFF, TRAIN_UNTIL, args.max_lots, seed=1)
    test, truth = build_examples(lots, bids, suppliers, TEST_CUTOFF, TEST_UNTIL, args.max_lots, seed=2)
    print(f"Обучение: {train['lot_id'].nunique()} лотов, {len(train)} строк")
    print(f"Проверка: {test['lot_id'].nunique()} лотов, {len(test)} строк")

    model = fit_ranker(train)
    results = {
        "Топ по победам": ranking_metrics(test, baseline_score(test), truth),
        "Формула": ranking_metrics(test, formula_score(test), truth),
        "LightGBM": ranking_metrics(test, pd.Series(model.predict(test[FEATURES]), index=test.index), truth),
    }
    print(pd.DataFrame(results).rename(index=METRIC_LABELS).round(3).to_string())

    final = fit_ranker(test)
    importance = pd.Series(final.booster_.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
    print("\nВажность признаков:")
    print((importance / importance.sum()).round(3).to_string())

    MODEL_DIR.mkdir(exist_ok=True)
    final.booster_.save_model(MODEL_DIR / "model.txt")
    (MODEL_DIR / "metrics.json").write_text(
        json.dumps({"features": FEATURES, "test_period": [TEST_CUTOFF, TEST_UNTIL], "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nМодель сохранена: {MODEL_DIR / 'model.txt'}")


if __name__ == "__main__":
    main()
