"""Общие фикстуры: гарантируют наличие датасета и обученной модели."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "connections.csv"
MODEL = ROOT / "artifacts" / "model.pkl"


def _run(module: str, script: str) -> None:
    subprocess.run([sys.executable, script], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)


@pytest.fixture(scope="session", autouse=True)
def prepared_project() -> None:
    if not CSV.exists():
        _run("make_dataset", "data/make_dataset.py")
    if not MODEL.exists():
        subprocess.run([sys.executable, "-m", "nids.train"], cwd=ROOT,
                       check=True, stdout=subprocess.DEVNULL)
