"""Обучение модели на data/connections.csv.

Результаты: artifacts/model.pkl и artifacts/metadata.json (метрики, параметры, seed).
Обучение детерминировано: фиксированы seed генерации данных, random_state модели
и stratify-разбиение, поэтому повторный запуск даёт те же метрики.
"""

from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from nids import FEATURES, encode

ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = ROOT / "data" / "connections.csv"
ARTIFACTS = ROOT / "artifacts"
SEED = 42


def load() -> tuple[list[list[float]], list[str]]:
    with CSV_PATH.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [encode(r) for r in rows], [r["label"] for r in rows]


def main() -> None:
    X, y = load()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=SEED, stratify=y
    )
    model = RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=1)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    metadata = {
        "model": "RandomForestClassifier",
        "n_estimators": 100,
        "random_state": SEED,
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "features": FEATURES,
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "f1_macro": round(float(f1_score(y_test, pred, average="macro")), 4),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with (ARTIFACTS / "model.pkl").open("wb") as fh:
        pickle.dump(model, fh)
    with (ARTIFACTS / "metadata.json").open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
