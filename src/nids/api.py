"""HTTP-сервис NIDS: /health и /predict."""

from __future__ import annotations

import os
import pickle
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from nids import PROTOCOLS, SERVICES

ROOT = Path(__file__).resolve().parent.parent.parent
# Путь к каталогу с моделью можно переопределить переменной окружения MODEL_DIR
# (в контейнере модель обычно подключают томом в /models).
MODEL_DIR = Path(os.environ.get("MODEL_DIR", ROOT / "artifacts"))
MODEL_PATH = MODEL_DIR / "model.pkl"

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
    return {"label": label, "confidence": round(proba, 4)}
