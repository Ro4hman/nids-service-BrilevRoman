"""HTTP-сервис NIDS: /health и /predict."""

from __future__ import annotations

import logging
import os
import pickle
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nids import PROTOCOLS, SERVICES
from nids.db import PredictionRow, log_safely

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("nids.api")

ROOT = Path(__file__).resolve().parent.parent.parent
# Путь к каталогу с моделью можно переопределить переменной окружения MODEL_DIR
# (в контейнере модель обычно подключают томом в /models).
MODEL_DIR = Path(os.environ.get("MODEL_DIR", ROOT / "artifacts"))
MODEL_PATH = MODEL_DIR / "model.pkl"
MODEL_VERSION = os.environ.get("MODEL_VERSION", "nids-rf-v0.1.0")

app = FastAPI(title="nids-service", version="0.1.0")
_model = None


def get_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise HTTPException(status_code=503, detail="model is not trained yet")
        with MODEL_PATH.open("rb") as fh:
            _model = pickle.load(fh)
    return _model


class Connection(BaseModel):
    src_port: int = 40000
    dst_port: int = 443
    duration_ms: float = 120
    bytes_in: float = 4000
    bytes_out: float = 3000
    packets: float = 20
    protocol: str = "tcp"
    service: str = "https"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
def predict(conn: Connection) -> dict:
    started = time.perf_counter()
    if conn.protocol not in PROTOCOLS or conn.service not in SERVICES:
        raise HTTPException(status_code=422, detail="unknown protocol or service")
    features = [[
        conn.src_port,
        conn.dst_port,
        conn.duration_ms,
        conn.bytes_in,
        conn.bytes_out,
        conn.packets,
        PROTOCOLS.index(conn.protocol),
        SERVICES.index(conn.service),
    ]]
    model = get_model()
    label = model.predict(features)[0]
    proba = float(max(model.predict_proba(features)[0]))
    response_ms = (time.perf_counter() - started) * 1000
    # Журнал пишется после расчёта: даже при недоступной базе ответ уже готов.
    log_safely(
        PredictionRow(
            model_version=MODEL_VERSION,
            src_port=conn.src_port,
            dst_port=conn.dst_port,
            duration_ms=conn.duration_ms,
            bytes_in=conn.bytes_in,
            bytes_out=conn.bytes_out,
            packets=conn.packets,
            protocol_type=conn.protocol,
            service=conn.service,
            prediction=str(label),
            probability=round(proba, 4),
            response_ms=round(response_ms, 3),
        )
    )
    return {
        "label": label,
        "confidence": round(proba, 4),
        "response_ms": round(response_ms, 3),
    }
