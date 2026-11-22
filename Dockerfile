# ---------- ступень 1: сборка ----------
FROM python:3.12-slim AS builder

WORKDIR /app

# Сначала только манифест зависимостей: этот слой переиспользуется из кэша,
# пока не менялся pyproject.toml. Изменение исходного кода его не сбрасывает.
COPY pyproject.toml ./
# Ставим только зависимости: пакет nids в эту ступень не устанавливается,
# код подключается через PYTHONPATH, иначе заглушка перекрыла бы реальные модули.
RUN pip install --no-cache-dir --prefix=/install \
    "scikit-learn>=1.3" "fastapi>=0.110" "uvicorn[standard]>=0.27" \
    "psycopg[binary]>=3.1"

ENV PYTHONPATH=/app/src:/install/lib/python3.12/site-packages

# Затем код и обучение модели
COPY src ./src
COPY data ./data
RUN python data/make_dataset.py && python -m nids.train \
    && rm -f data/connections.csv

# ---------- ступень 2: рантайм ----------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Обновляем пакеты базового образа: в python:3.12-slim периодически висят
# уязвимости уровня HIGH с уже выпущенным исправлением в Debian (например,
# zlib1g CVE-2026-85091). Без этого шага Trivy валит сборку с exit-code 1.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Только установленные пакеты из ступени сборки
COPY --from=builder /install /usr/local

# Код приложения и обученная модель
COPY --from=builder /app/src ./src
COPY --from=builder /app/artifacts ./artifacts

# Непривилегированный пользователь
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "nids.api:app", "--host", "0.0.0.0", "--port", "8000"]
