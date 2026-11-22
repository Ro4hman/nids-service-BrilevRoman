# nids-service — сервис обнаружения сетевых вторжений

Сквозной проект курса «Инструментальные средства разработки инфокоммуникационных
систем с ИИ». Сервис принимает признаки сетевого соединения и возвращает оценку
вероятности того, что соединение является атакой.

## Состав

```
nids-service-BrilevRoman/
├── AUTHOR.md            # сведения об авторе
├── Dockerfile           # многоступенчатая сборка образа
├── Dockerfile.v1-naive  # «наивный» вариант для сравнения (лабораторная №3)
├── data/
│   └── make_dataset.py  # генератор датасета connections.csv
├── labs/                # отчёты по лабораторным работам
├── pyproject.toml       # зависимости и настройки пакета
├── scripts/
│   └── stats.sh         # статистика по CSV
├── src/
│   ├── app.py           # простой HTTP-сервис (stdlib), GET /health
│   └── nids/
│       ├── __init__.py  # признаки и справочники protocol/service
│       ├── api.py       # FastAPI: /health и /predict
│       └── train.py     # обучение модели, artifacts/
└── tests/               # pytest: модель и API
```

## Запуск без контейнера

Нужен Python 3.10+ и `pip`.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python data/make_dataset.py        # сгенерировать data/connections.csv (500 строк)
python -m nids.train               # обучить модель: artifacts/model.pkl + metadata.json
uvicorn nids.api:app --app-dir src --port 8000 --reload
```

Проверка:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"protocol":"tcp","service":"https","dst_port":443}'
```

Документация API — `http://localhost:8000/docs`.

## Тесты

```bash
pytest
```

Шесть тестов: контракт `/health` и `/predict` (включая ответ `422` на неизвестный
протокол) и проверки обученной модели (файл `artifacts/model.pkl`, точность выше
порогового уровня). Датасет и модель при отсутствии создаются автоматически
фикстурой `tests/conftest.py`, поэтому заранее запускать `train` не нужно.

## Качество модели

Датасет `data/connections.csv`: 500 соединений, seed 42, классы `normal`, `dos`,
`probe`, `r2l`. Модель — `RandomForestClassifier`, 100 деревьев.

| Метрика | Значение |
|---|---|
| accuracy | 0,992 |
| f1_macro | 0,9557 |

Метрики пишутся в `artifacts/metadata.json` вместе с параметрами обучения, поэтому
результат воспроизводим: при том же seed повторный запуск `python -m nids.train`
даёт те же числа.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `MODEL_DIR` | `artifacts` | каталог, где ищется `model.pkl` |

Пригодится, когда артефакты подключаются томом в контейнер.

## Запуск в контейнере

Модель обучается во время сборки образа, поэтому контейнер самодостаточен: датасет
и обученный `model.pkl` в образ не копируются, а создаются внутри.

Сборка:

```bash
docker build -t nids-service:v2 .
```

Запуск с пробросом порта:

```bash
docker run -d --name nids -p 8000:8000 nids-service:v2
```

Проверка:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"src_port":40000,"dst_port":443,"duration_ms":120,"bytes_in":4000,
       "bytes_out":3000,"packets":20,"protocol":"tcp","service":"https"}'
```

Интерактивная документация — `http://localhost:8000/docs`.

### Модель из внешнего каталога

Приложение читает модель из каталога `artifacts/`, а переменная окружения
`MODEL_DIR` позволяет указать другой путь. Это удобно, чтобы подменять модель без
пересборки образа:

```bash
docker run -d --name nids -p 8000:8000 \
  -v "$PWD/artifacts:/models:ro" \
  -e MODEL_DIR=/models \
  nids-service:v2
```

Если файл модели недоступен, `/predict` отвечает `503` с текстом
`model is not trained yet`, а `/health` продолжает работать.

### Параметры образа

| Параметр | Значение |
|---|---|
| Базовый образ | `python:3.12-slim` |
| Пользователь процесса | `appuser` (непривилегированный) |
| Порт | `8000` |
| `PYTHONPATH` | `/app/src` |
| Размер образа `v2` | 590 МБ |
