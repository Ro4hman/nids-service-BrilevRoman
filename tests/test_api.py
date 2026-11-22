"""Тесты HTTP-интерфейса сервиса."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nids.api import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_returns_label() -> None:
    response = client.post(
        "/predict",
        json={
            "src_port": 51000,
            "dst_port": 80,
            "duration_ms": 880,
            "bytes_in": 210,
            "bytes_out": 14800,
            "packets": 118,
            "protocol": "tcp",
            "service": "http",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["label"] in {"normal", "dos", "probe", "r2l"}
    assert 0.0 <= body["confidence"] <= 1.0


def test_predict_rejects_unknown_protocol() -> None:
    response = client.post("/predict", json={"protocol": "sctp"})
    assert response.status_code == 422
