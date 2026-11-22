"""Тест порога качества модели.

Контрактные тесты проверяют форму ответа. Этот тест проверяет назначение системы:
метрика качества обученной модели не должна опускаться ниже согласованного порога.
Порог берётся из metadata.json, который пишет src/nids/train.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
METADATA = ROOT / "artifacts" / "metadata.json"

F1_THRESHOLD = 0.85


@pytest.fixture(scope="module")
def metadata() -> dict:
    if not METADATA.exists():
        pytest.skip("metadata.json отсутствует: модель ещё не обучена")
    return json.loads(METADATA.read_text(encoding="utf-8"))


def test_f1_meets_threshold(metadata: dict) -> None:
    """F1_macro обученной модели не ниже 0,85."""
    f1 = metadata["f1_macro"]
    assert f1 >= F1_THRESHOLD, (
        f"качество модели упало: f1_macro={f1} < порога {F1_THRESHOLD}"
    )


def test_accuracy_meets_threshold(metadata: dict) -> None:
    """Точность обученной модели не ниже 0,90."""
    accuracy = metadata["accuracy"]
    assert accuracy >= 0.90, (
        f"качество модели упало: accuracy={accuracy} < порога 0.90"
    )
