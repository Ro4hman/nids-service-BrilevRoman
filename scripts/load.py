"""Нагрузочный скрипт: N запросов на /predict по данным data/connections.csv.

Использование:
    python scripts/load.py                 # 500 запросов на http://127.0.0.1:8000
    python scripts/load.py --n 1000 --url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "connections.csv"


def payload(row: dict) -> dict:
    return {
        "src_port": int(row["src_port"]),
        "dst_port": int(row["dst_port"]),
        "duration_ms": float(row["duration_ms"]),
        "bytes_in": float(row["bytes_in"]),
        "bytes_out": float(row["bytes_out"]),
        "packets": float(row["packets"]),
        "protocol": row["protocol"],
        "service": row["service"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Нагрузка на /predict")
    parser.add_argument("--n", type=int, default=500, help="число запросов")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="базовый URL")
    args = parser.parse_args()

    with CSV_PATH.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    random.seed(42)
    labels: dict[str, int] = {}
    errors = 0
    started = time.perf_counter()

    for i in range(args.n):
        body = json.dumps(payload(random.choice(rows))).encode()
        req = urllib.request.Request(
            f"{args.url}/predict",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            labels[data["label"]] = labels.get(data["label"], 0) + 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 3:
                print(f"error: {exc}", file=sys.stderr)

    elapsed = time.perf_counter() - started
    print(f"requests: {args.n}, errors: {errors}, elapsed: {elapsed:.2f} s")
    print(f"rps: {args.n / elapsed:.1f}")
    print("labels:", dict(sorted(labels.items())))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
