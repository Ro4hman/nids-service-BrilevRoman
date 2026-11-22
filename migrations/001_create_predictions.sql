-- 001_create_predictions.sql
-- Журнал предсказаний сервиса nids-service.
-- Применение: docker exec -i nids-db psql -U nids -d nids < migrations/001_create_predictions.sql

CREATE TABLE IF NOT EXISTS predictions (
    id             BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version  TEXT        NOT NULL,
    src_port       INTEGER     NOT NULL,
    dst_port       INTEGER     NOT NULL,
    duration_ms    REAL        NOT NULL,
    bytes_in       REAL        NOT NULL,
    bytes_out      REAL        NOT NULL,
    packets        REAL        NOT NULL,
    protocol_type  TEXT        NOT NULL,
    service        TEXT        NOT NULL,
    prediction     TEXT        NOT NULL,
    probability    REAL        NOT NULL,
    response_ms    REAL        NOT NULL
);

CREATE INDEX IF NOT EXISTS predictions_prediction_idx ON predictions (prediction);
