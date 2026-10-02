import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml.data import load_all
from ml.features import FEATURES, build_examples
from ml.text import lot_typicality

MODEL_DIR = Path(__file__).resolve().parent / "model"
CALIBRATION_CUTOFF, CALIBRATION_UNTIL = "2025-06-30", "2025-09-30"
BIN_EDGES = np.linspace(0, 1, 11)
CALIBRATOR_FILE = "calibration.txt"
MAX_PROBABILITY = 0.7


def reliability_table(probability: np.ndarray, labels: np.ndarray) -> list[dict]:
    frame = pd.DataFrame({"predicted": probability, "actual": labels})
    frame["bin"] = pd.cut(frame["predicted"], BIN_EDGES, include_lowest=True)
    table = frame.groupby("bin", observed=True).agg(
        predicted=("predicted", "mean"),
        actual=("actual", "mean"),
        rows=("actual", "size"),
    )
    return [
        {"range": f"{interval.left:.0%}–{interval.right:.0%}", **{key: round(float(value), 3) for key, value in row.items()}}
        for interval, row in table.iterrows()
    ]


CALIBRATION_FEATURES = ["raw", "gap", "rank"]
CALIBRATION_PARAMS = {
    "objective": "binary",
    "n_estimators": 150,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_child_samples": 500,
    "monotone_constraints": [1, 1, -1],
    "verbose": -1,
}


def calibration_frame(raw: np.ndarray, lot_ids: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame({"lot_id": lot_ids, "raw": raw})
    frame["gap"] = frame["raw"] - frame.groupby("lot_id")["raw"].transform("max")
    frame["rank"] = frame.groupby("lot_id")["raw"].rank(ascending=False, method="first")
    return frame


def fit_calibration(booster: lgb.Booster, examples: pd.DataFrame) -> tuple[lgb.Booster, dict]:
    frame = calibration_frame(booster.predict(examples[FEATURES]), examples["lot_id"].to_numpy())
    labels = examples["participated"].to_numpy()
    lots = frame["lot_id"].unique()
    fit_lots = set(np.random.default_rng(0).choice(lots, size=len(lots) // 2, replace=False))
    fit_mask = frame["lot_id"].isin(fit_lots).to_numpy()
    classifier = lgb.LGBMClassifier(**CALIBRATION_PARAMS)
    classifier.fit(frame.loc[fit_mask, CALIBRATION_FEATURES], labels[fit_mask])
    check = frame.loc[~fit_mask]
    probability = np.minimum(classifier.predict_proba(check[CALIBRATION_FEATURES])[:, 1], MAX_PROBABILITY)
    actual = labels[~fit_mask]
    top = (check["rank"] == 1).to_numpy()
    return classifier.booster_, {
        "features": CALIBRATION_FEATURES,
        "maxProbability": MAX_PROBABILITY,
        "baseRate": round(float(actual.mean()), 4),
        "target": "participated",
        "period": [CALIBRATION_CUTOFF, CALIBRATION_UNTIL],
        "lots": int(len(lots) - len(fit_lots)),
        "top_predicted": round(float(probability[top].mean()), 3),
        "top_actual": round(float(actual[top].mean()), 3),
        "reliability": reliability_table(probability, actual),
        "top_reliability": reliability_table(probability[top], actual[top]),
    }


def print_calibration(calibration: dict) -> None:
    print(f"\nКалибровка на {calibration['lots']} лотах {calibration['period'][0]} … {calibration['period'][1]}")
    print(f"{'Обещали':>10} {'Средний прогноз':>16} {'Участвовали':>12} {'Строк':>8}")
    for row in calibration["reliability"]:
        print(f"{row['range']:>10} {row['predicted']:>16.1%} {row['actual']:>12.1%} {int(row['rows']):>8}")
    print("Только первые в списке:")
    for row in calibration["top_reliability"]:
        print(f"{row['range']:>10} {row['predicted']:>16.1%} {row['actual']:>12.1%} {int(row['rows']):>8}")
    print(f"Первый в списке: обещали {calibration['top_predicted']:.1%}, участвовал в {calibration['top_actual']:.1%} лотов")


def save_calibration(calibrator: lgb.Booster, calibration: dict) -> None:
    calibrator.save_model(MODEL_DIR / CALIBRATOR_FILE)
    path = MODEL_DIR / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    metrics["calibration"] = calibration
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    lots, bids, suppliers = load_all()
    typicality = lot_typicality(lots)
    examples, _ = build_examples(
        lots, bids, suppliers, CALIBRATION_CUTOFF, CALIBRATION_UNTIL, 30000, seed=1, typicality=typicality
    )
    lines = (MODEL_DIR / "model.txt").read_text(encoding="utf-8").splitlines()
    booster = lgb.Booster(model_str="\n".join(lines) + "\n")
    calibrator, calibration = fit_calibration(booster, examples)
    print_calibration(calibration)
    save_calibration(calibrator, calibration)
    print(f"\nКоэффициенты сохранены в {MODEL_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
