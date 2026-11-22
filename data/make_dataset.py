"""Генерация синтетического датасета сетевых соединений (детерминированно).

Колонки: id,ts,src_ip,src_port,dst_ip,dst_port,protocol,duration_ms,
bytes_in,bytes_out,packets,flags,service,state,label
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "connections.csv"
ROWS = 500
SEED = 42

PROTOCOLS = ["tcp", "udp", "icmp"]
SERVICES = ["http", "https", "dns", "ssh", "smtp", "ftp"]
STATES = ["S0", "SF", "REJ"]
FLAGS = ["S", "SA", "RA", "FA"]
LABELS = ["normal", "dos", "probe", "r2l"]


def _connection(rng: random.Random, idx: int) -> list:
    label = rng.choices(LABELS, weights=[70, 15, 10, 5])[0]
    proto = rng.choice(PROTOCOLS)
    service = rng.choice(SERVICES)
    base_duration = {"normal": 120, "dos": 900, "probe": 60, "r2l": 300}[label]
    duration = max(1, int(rng.gauss(base_duration, base_duration * 0.25)))
    bytes_in = max(0, int(rng.gauss(
        {"normal": 4000, "dos": 200, "probe": 800, "r2l": 1500}[label], 500
    )))
    bytes_out = max(0, int(rng.gauss(
        {"normal": 3000, "dos": 15000, "probe": 300, "r2l": 600}[label], 900
    )))
    packets = max(1, int(rng.gauss({"normal": 20, "dos": 120, "probe": 5, "r2l": 12}[label], 4)))
    state = rng.choices(STATES, weights=[10, 75, 15])[0]
    if label == "dos":
        state = "REJ"
    return [
        idx,
        f"2026-11-22T10:{idx % 60:02d}:00",
        f"10.0.{rng.randint(0, 3)}.{rng.randint(2, 254)}",
        rng.randint(1024, 65535),
        f"172.16.0.{rng.randint(2, 20)}",
        rng.choice([53, 80, 443, 22, 25, 21]),
        proto,
        duration,
        bytes_in,
        bytes_out,
        packets,
        rng.choice(FLAGS),
        service,
        state,
        label,
    ]


def main() -> None:
    rng = random.Random(SEED)
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "id", "ts", "src_ip", "src_port", "dst_ip", "dst_port", "protocol",
        "duration_ms", "bytes_in", "bytes_out", "packets", "flags",
        "service", "state", "label",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(1, ROWS + 1):
            writer.writerow(_connection(rng, i))
    print(f"written: {CSV_PATH} ({ROWS} rows)")


if __name__ == "__main__":
    main()
