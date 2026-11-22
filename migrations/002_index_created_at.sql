-- 002_index_created_at.sql
-- Индекс по времени создания записи журнала.
-- Применение: docker exec -i nids-db psql -U nids -d nids < migrations/002_index_created_at.sql

CREATE INDEX IF NOT EXISTS predictions_created_at_idx
    ON predictions (created_at);
