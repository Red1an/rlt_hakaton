import argparse
import json
import time
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from ml.calibrate import CALIBRATOR_FILE, fit_calibration, print_calibration
from ml.data import load_all
from ml.features import FEATURES, baseline_score, build_examples, formula_score
from ml.metrics import TOP_K, ranking_metrics
from ml.text import lot_typicality, save_typicality

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


STARTED = time.perf_counter()
PROGRESS_EVERY = 50


def log(message: str) -> None:
    print(f"[{time.perf_counter() - STARTED:6.0f} с] {message}", flush=True)


def tree_progress(env: lgb.callback.CallbackEnv) -> None:
    done = env.iteration + 1
    if done % PROGRESS_EVERY == 0 or done == env.end_iteration:
        log(f"  деревьев {done} из {env.end_iteration}")


def fit_ranker(rows: pd.DataFrame) -> lgb.LGBMRanker:
    rows = rows.sort_values("lot_id")
    model = lgb.LGBMRanker(**MODEL_PARAMS)
    model.fit(
        rows[FEATURES],
        rows["participated"] + rows["won"],
        group=rows.groupby("lot_id").size().values,
        callbacks=[tree_progress],
    )
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение модели ранжирования поставщиков")
    parser.add_argument("--max-lots", type=int, default=30000)
    parser.add_argument("--refresh", action="store_true", help="заново выгрузить данные из базы")
    args = parser.parse_args()

    log("Загрузка данных")
    lots, bids, suppliers = load_all(args.refresh)
    log("Типичность лотов по предмету закупки")
    typicality = lot_typicality(lots, args.refresh)
    log("Примеры для обучения")
    train, _ = build_examples(lots, bids, suppliers, TRAIN_CUTOFF, TRAIN_UNTIL, args.max_lots, seed=1, typicality=typicality)
    log("Примеры для проверки")
    test, truth = build_examples(lots, bids, suppliers, TEST_CUTOFF, TEST_UNTIL, args.max_lots, seed=2, typicality=typicality)
    print(f"Обучение: {train['lot_id'].nunique()} лотов, {len(train)} строк")
    print(f"Проверка: {test['lot_id'].nunique()} лотов, {len(test)} строк")

    log("Обучение модели для проверки")
    model = fit_ranker(train)
    log("Метрики")
    results = {
        "Топ по победам": ranking_metrics(test, baseline_score(test), truth),
        "Формула": ranking_metrics(test, formula_score(test), truth),
        "LightGBM": ranking_metrics(test, pd.Series(model.predict(test[FEATURES]), index=test.index), truth),
    }
    print(pd.DataFrame(results).rename(index=METRIC_LABELS).round(3).to_string())

    log("Обучение итоговой модели на последнем квартале")
    final = fit_ranker(test)
    importance = pd.Series(final.booster_.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
    print("\nВажность признаков:")
    print((importance / importance.sum()).round(3).to_string())

    log("Калибровка вероятностей на лотах, которых итоговая модель не видела")
    calibrator, calibration = fit_calibration(final.booster_, train)
    print_calibration(calibration)

    MODEL_DIR.mkdir(exist_ok=True)
    final.booster_.save_model(MODEL_DIR / "model.txt")
    calibrator.save_model(MODEL_DIR / CALIBRATOR_FILE)
    save_typicality(typicality, MODEL_DIR)
    (MODEL_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "features": FEATURES,
                "test_period": [TEST_CUTOFF, TEST_UNTIL],
                "results": results,
                "calibration": calibration,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nМодель сохранена: {MODEL_DIR / 'model.txt'}")


if __name__ == "__main__":
    main()
