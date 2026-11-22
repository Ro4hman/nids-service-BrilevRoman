"""Тесты конвейера данных и обучения."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "connections.csv"
META = ROOT / "artifacts" / "metadata.json"


def test_dataset_header_and_size() -> None:
    with CSV.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][-1] == "label"
    assert len(rows) - 1 == 500                       # 500 соединений + заголовок
    assert all(len(r) == 15 for r in rows)            # ровно 15 колонок


def test_dataset_is_deterministic() -> None:
    with CSV.open(encoding="utf-8") as fh:
        first = fh.readline()
    assert first.startswith("id,ts,src_ip")


def test_metadata_metrics() -> None:
    meta = json.loads(META.read_text(encoding="utf-8"))
    assert meta["random_state"] == 42
    assert meta["n_train"] + meta["n_test"] == meta["n_samples"]
    assert meta["accuracy"] >= 0.8
