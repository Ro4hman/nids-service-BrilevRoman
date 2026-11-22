"""Работа с PostgreSQL: журнал предсказаний.

Параметры подключения берутся только из переменной окружения DATABASE_URL,
секретов в коде нет. Ошибки базы не должны ронять выдачу предсказания,
поэтому наружу они отдаются исключением, а обрабатываются в api.py.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

log = logging.getLogger("nids.db")

DATABASE_URL = os.environ.get("DATABASE_URL")

INSERT_SQL = """
INSERT INTO predictions (
    created_at, model_version, src_port, dst_port, duration_ms,
    bytes_in, bytes_out, packets, protocol_type, service,
    prediction, probability, response_ms
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass
class PredictionRow:
    model_version: str
    src_port: int
    dst_port: int
    duration_ms: float
    bytes_in: float
    bytes_out: float
    packets: float
    protocol_type: str
    service: str
    prediction: str
    probability: float
    response_ms: float


def connect() -> psycopg.Connection:
    """Открывает короткое соединение с базой (таймаут — чтобы не ждать отказа)."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, connect_timeout=2)


def save_prediction(row: PredictionRow) -> None:
    """Пишет одну строку журнала. Исключение пробрасывается вызывающему коду."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            INSERT_SQL,
            (
                datetime.now(timezone.utc),
                row.model_version,
                row.src_port,
                row.dst_port,
                row.duration_ms,
                row.bytes_in,
                row.bytes_out,
                row.packets,
                row.protocol_type,
                row.service,
                row.prediction,
                row.probability,
                row.response_ms,
            ),
        )
        conn.commit()


def log_safely(row: PredictionRow) -> None:
    """Пытается записать строку, но никогда не роняет запрос пользователя."""
    try:
        save_prediction(row)
    except Exception as exc:  # noqa: BLE001 — журнал не должен ломать сервис
        log.warning("failed to write prediction log: %s", exc)
