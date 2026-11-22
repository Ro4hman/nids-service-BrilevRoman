# Лабораторная работа №4. Базы данных. PostgreSQL и журнал предсказаний

**Автор:** Бырлёв Роман Александрович, группа ИСТм-21.
**Репозиторий:** <https://github.com/Ro4hman/nids-service-BrilevRoman>
**Ветка:** `feature/database`.

## 1. Цель работы

Подключить к сервису обнаружения вторжений реляционную базу данных: развернуть
PostgreSQL в контейнере, описать схему журнала предсказаний миграцией, писать журнал
из обработчика `/predict` так, чтобы недоступность базы не ломала ответ, и оценить
журнал аналитическими SQL-запросами и планами выполнения.

## 2. Ход работы

### 2.1. Ветка и зависимости

```bash
$ git switch -c feature/database
Switched to a new branch 'feature/database'
$ ./.venv/Scripts/python.exe -m pip install -e ".[dev]"
$ ./.venv/Scripts/python.exe -c "import psycopg; print(psycopg.__version__)"
3.3.9
```

В `pyproject.toml` добавлена зависимость `psycopg[binary]>=3.1` — бинарная сборка
драйвера не требует компилятора в контейнере.

### 2.2. База в контейнере

```bash
$ docker run -d --name nids-db \
    -e POSTGRES_PASSWORD=devpassword \
    -e POSTGRES_USER=nids \
    -e POSTGRES_DB=nids \
    -p 5432:5432 \
    -v nids-pgdata:/var/lib/postgresql/data \
    postgres:16-alpine
c310ca3e043dd3a92db9b0f9fff527bacc25e12fdeee20d1e87e4dfcdb2613e6

$ docker ps --filter name=nids-db --format '{{.Names}} {{.Status}} {{.Ports}}'
nids-db Up 8 seconds 0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp

$ docker exec nids-db psql -U nids -d nids -c "SELECT version();"
                                         version
------------------------------------------------------------------------------------------
 PostgreSQL 16.16 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
(1 row)
```

### 2.3. Эксперимент с томом: что будет без `-v`

Смысл опыта — показать, что данные PostgreSQL живут не в контейнере, а в томе.
Основной контейнер удаляется, на его месте поднимается точно такой же, но **без**
`-v nids-pgdata:/var/lib/postgresql/data`; миграция применяется к пустому каталогу
данных, и таблица оказывается пустой.

```bash
$ docker exec nids-db psql -U nids -d nids -t -c "SELECT count(*) FROM predictions;"
503

$ docker rm -f nids-db
nids-db

$ docker run -d --name nids-db-novol \
    -e POSTGRES_PASSWORD=devpassword -e POSTGRES_USER=nids -e POSTGRES_DB=nids \
    -p 5433:5432 postgres:16-alpine          # ключа -v нет
$ docker exec -i nids-db-novol psql -U nids -d nids < migrations/001_create_predictions.sql
CREATE TABLE
CREATE INDEX

$ docker exec nids-db-novol psql -U nids -d nids -c "SELECT count(*) FROM predictions;"
 count
-------
     0
(1 row)
```

Возврат к тому же тому — данные на месте:

```bash
$ docker rm -f nids-db-novol
$ docker run -d --name nids-db -e POSTGRES_PASSWORD=devpassword -e POSTGRES_USER=nids \
    -e POSTGRES_DB=nids -p 5432:5432 -v nids-pgdata:/var/lib/postgresql/data \
    postgres:16-alpine
$ docker exec nids-db psql -U nids -d nids -c "SELECT count(*) FROM predictions;"
 count
-------
   503
(1 row)
```

Вывод: без тома файлы базы лежат в записываемом слое контейнера и пропадают вместе
с ним; с томом контейнер — расходуемый объект, а состояние переживает пересоздание.

### 2.4. Миграция схемы

`migrations/001_create_predictions.sql`:

```sql
CREATE TABLE IF NOT EXISTS predictions (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
```

Применение и проверка схемы:

```bash
$ docker exec -i nids-db psql -U nids -d nids < migrations/001_create_predictions.sql
CREATE TABLE
CREATE INDEX

$ docker exec nids-db psql -U nids -d nids -c "\d predictions"
                                        Table "public.predictions"
    Column     |           Type           | Collation | Nullable |             Default
---------------+--------------------------+-----------+----------+----------------------------------
 id            | bigint                   |           | not null | nextval('predictions_id_seq'::regclass)
 created_at    | timestamp with time zone |           | not null | now()
 model_version | text                     |           | not null |
 src_port      | integer                  |           | not null |
 dst_port      | integer                  |           | not null |
 duration_ms   | real                     |           | not null |
 bytes_in      | real                     |           | not null |
 bytes_out     | real                     |           | not null |
 packets       | real                     |           | not null |
 protocol_type | text                     |           | not null |
 service       | text                     |           | not null |
 prediction    | text                     |           | not null |
 probability   | real                     |           | not null |
 response_ms   | real                     |           | not null |
Indexes:
    "predictions_pkey" PRIMARY KEY, btree (id)
    "predictions_prediction_idx" btree (prediction)
```

### 2.5. Модуль доступа к базе и запись из сервиса

`src/nids/db.py` — короткое соединение на запись, параметры только из окружения:

```python
DATABASE_URL = os.environ.get("DATABASE_URL")

INSERT_SQL = """
INSERT INTO predictions (
    created_at, model_version, src_port, dst_port, duration_ms,
    bytes_in, bytes_out, packets, protocol_type, service,
    prediction, probability, response_ms
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def connect() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL, connect_timeout=2)


def log_safely(row: PredictionRow) -> None:
    """Пытается записать строку, но никогда не роняет запрос пользователя."""
    try:
        save_prediction(row)
    except Exception as exc:
        log.warning("failed to write prediction log: %s", exc)
```

В `/predict` время ответа измеряется вокруг расчёта, а запись журнала выполняется
после того, как ответ уже сформирован:

```python
@app.post("/predict")
def predict(conn: Connection) -> dict:
    started = time.perf_counter()
    ...
    label = model.predict(features)[0]
    proba = float(max(model.predict_proba(features)[0]))
    response_ms = (time.perf_counter() - started) * 1000
    log_safely(PredictionRow(model_version=MODEL_VERSION, ..., response_ms=response_ms))
    return {"label": label, "confidence": round(proba, 4),
            "response_ms": round(response_ms, 3)}
```

### 2.6. Тесты

```bash
$ ./.venv/Scripts/python.exe -m pytest -q
6 passed, 1 warning in 3.50s
```

### 2.7. Нагрузка: 500 запросов на `/predict`

```bash
$ docker exec nids-db psql -U nids -d nids -c "SELECT count(*) FROM predictions;"
 count
-------
     0

$ export DATABASE_URL="postgresql://nids:devpassword@localhost:5432/nids"
$ ./.venv/Scripts/python.exe -m uvicorn nids.api:app --app-dir src --port 8000
INFO:     Application startup complete.

$ ./.venv/Scripts/python.exe scripts/load.py --n 500
requests: 500, errors: 0, elapsed: 21.61 s
rps: 23.1
labels: {'dos': 73, 'normal': 353, 'probe': 58, 'r2l': 16}
```

Все 500 запросов получили ответ, ошибок нет; распределение меток совпадает с
распределением классов в датасете, то есть нагрузка шла по реальным строкам
`data/connections.csv`.

### 2.8. Шесть аналитических запросов

**1. Всего предсказаний и доля атак.**

```sql
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE prediction <> 'normal') AS attacks,
       ROUND(100.0 * COUNT(*) FILTER (WHERE prediction <> 'normal') / COUNT(*), 2)
           AS attack_pct
FROM predictions;
```

```
 total | attacks | attack_pct
-------+---------+------------
   502 |     149 |      29.68
```

Чуть меньше трети соединений модель сочла атаками — это соответствует доле
аномальных классов в датасете.

**2. Атаки и нормальный трафик по протоколам.**

```sql
SELECT protocol_type,
       COUNT(*) FILTER (WHERE prediction <> 'normal') AS attacks,
       COUNT(*) FILTER (WHERE prediction = 'normal')  AS normal
FROM predictions
GROUP BY protocol_type
ORDER BY protocol_type;
```

```
 protocol_type | attacks | normal
---------------+---------+--------
 icmp          |      57 |    114
 tcp           |      47 |    125
 udp           |      45 |    114
```

Атаки распределены по протоколам почти равномерно, заметного перекоса в сторону
одного протокола нет.

**3. Активность по часам за последние сутки.**

```sql
SELECT date_trunc('hour', created_at) AS hour,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE prediction <> 'normal') AS attacks
FROM predictions
WHERE created_at > now() - interval '24 hours'
GROUP BY 1
ORDER BY 1;
```

```
          hour          |  n  | attacks
------------------------+-----+---------
 2026-11-22 13:00:00+00 | 502 |     149
(1 row)
```

Весь объём попал в один час: нагрузка подавалась одним прогоном, а не распределялась
по суткам.

**4. Статистика вероятности по классам.**

```sql
SELECT prediction,
       ROUND(AVG(probability)::numeric, 4) AS avg_p,
       ROUND(MIN(probability)::numeric, 4) AS min_p,
       ROUND(MAX(probability)::numeric, 4) AS max_p
FROM predictions
GROUP BY prediction
ORDER BY prediction;
```

```
 prediction | avg_p  | min_p | max_p
------------+--------+-------+-------
 dos        | 0.9952 | 0.9200 | 1.0000
 normal     | 0.9965 | 0.8400 | 1.0000
 probe      | 0.9572 | 0.4800 | 1.0000
 r2l        | 0.7869 | 0.5800 | 0.9500
(4 rows)
```

Чем реже класс в датасете, тем ниже и менее устойчива уверенность модели: у `r2l`
минимум вероятности `0,58`, у частых классов — почти единица.

**5. Топ-5 сервисов по доле срабатываний (не менее 10 наблюдений).**

```sql
SELECT service,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE prediction <> 'normal') AS attacks,
       ROUND(100.0 * COUNT(*) FILTER (WHERE prediction <> 'normal') / COUNT(*), 1)
           AS pct
FROM predictions
GROUP BY service
HAVING COUNT(*) >= 10
ORDER BY pct DESC, total DESC
LIMIT 5;
```

```
 service | total | attacks | pct
---------+-------+---------+------
 dns     |    68 |      27 | 39.7
 ssh     |   103 |      40 | 38.8
 http    |    83 |      26 | 31.3
 https   |    84 |      22 | 26.2
 ftp     |    90 |      19 | 21.1
(5 rows)
```

Максимальная доля атак — у DNS и SSH (около 39 %), минимальная — у FTP; различие
невелико и объясняется тем, что в синтетическом датасете класс не зависит от сервиса.

**6. Перцентили времени ответа.**

```sql
SELECT ROUND(percentile_cont(0.5)  WITHIN GROUP (ORDER BY response_ms)::numeric, 3) AS p50,
       ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY response_ms)::numeric, 3) AS p95,
       ROUND(percentile_cont(0.99) WITHIN GROUP (ORDER BY response_ms)::numeric, 3) AS p99
FROM predictions;
```

```
  p50  |  p95   |  p99
-------+--------+--------
 9.996 | 13.759 | 17.597
(1 row)
```

Медиана около 10 мс, а «хвост» распределения короткий: 99-й перцентиль лишь в 1,8
раза больше медианы, то есть отдельных «залипающих» запросов нет.

### 2.9. Индекс по `created_at`: `EXPLAIN ANALYZE` до и после

Миграция `migrations/002_index_created_at.sql`:

```sql
CREATE INDEX IF NOT EXISTS predictions_created_at_idx ON predictions (created_at);
```

**До индекса.**

```sql
EXPLAIN ANALYZE SELECT COUNT(*) FROM predictions
WHERE created_at >= now() - interval '1 hour';
```

```
 Aggregate  (cost=16.38..16.39 rows=1 width=8) (actual time=0.053..0.053 rows=1 loops=1)
   ->  Seq Scan on predictions  (cost=0.00..15.21 rows=469 width=0)
       (actual time=0.005..0.038 rows=502 loops=1)
         Filter: (created_at >= (now() - '01:00:00'::interval))
 Planning Time: 0.602 ms
 Execution Time: 0.108 ms
```

```sql
EXPLAIN ANALYZE SELECT id, response_ms FROM predictions
WHERE created_at > now() - interval '1 hour'
ORDER BY created_at DESC LIMIT 10;
```

```
 Limit  (cost=25.34..25.37 rows=10 width=20) (actual time=0.147..0.148 rows=10 loops=1)
   ->  Sort  (cost=25.34..26.51 rows=469 width=20) (actual time=0.146..0.146 rows=10 loops=1)
         Sort Key: created_at DESC
         Sort Method: top-N heapsort  Memory: 26kB
         ->  Seq Scan on predictions  (cost=0.00..15.21 rows=469 width=20)
             (actual time=0.005..0.062 rows=502 loops=1)
               Filter: (created_at > (now() - '01:00:00'::interval))
 Planning Time: 0.670 ms
 Execution Time: 0.189 ms
```

**После создания индекса и `ANALYZE predictions`.**

```bash
$ docker exec -i nids-db psql -U nids -d nids < migrations/002_index_created_at.sql
CREATE INDEX
$ docker exec nids-db psql -U nids -d nids -c "ANALYZE predictions;"
ANALYZE
```

```
 Aggregate  (cost=17.04..17.05 rows=1 width=8) (actual time=0.051..0.052 rows=1 loops=1)
   ->  Seq Scan on predictions  (cost=0.00..15.79 rows=502 width=0)
       (actual time=0.004..0.036 rows=502 loops=1)
         Filter: (created_at >= (now() - '01:00:00'::interval))
 Planning Time: 0.904 ms
 Execution Time: 0.111 ms
```

```
 Limit  (cost=0.28..0.97 rows=10 width=20) (actual time=0.029..0.030 loops=1)
   ->  Index Scan Backward using predictions_created_at_idx on predictions
       (cost=0.28..35.06 rows=502 width=20) (actual time=0.029..0.030 rows=10 loops=1)
         Index Cond: (created_at > (now() - '01:00:00'::interval))
 Planning Time: 0.821 ms
 Execution Time: 0.074 ms
```

| Запрос | План до | Время до | План после | Время после |
|---|---|---|---|---|
| `COUNT(*)` за час | `Seq Scan` | 0,108 мс | `Seq Scan` | 0,111 мс |
| `ORDER BY ... LIMIT 10` | `Sort` + `Seq Scan` | 0,189 мс | `Index Scan Backward` | 0,074 мс |

Запрос с сортировкой ускорился в 2,5 раза и сменил план: индекс отдаёт строки уже в
нужном порядке, сортировка исчезла. Агрегат `COUNT(*)` так и остался на `Seq Scan`:
читать нужно всю таблицу целиком, и индекс здесь только добавил бы обращения к ней
через кучу. При 502 строках разница в микросекундах, на объёме в миллионы строк
`Index Scan` даёт выигрыш на порядки.

### 2.10. Поведение при недоступной базе

```bash
$ docker stop nids-db
nids-db

$ curl -s -m 20 -X POST localhost:8000/predict -H "Content-Type: application/json" \
    -d '{"src_port":51000,"dst_port":80,"duration_ms":880,"bytes_in":210,
         "bytes_out":14800,"packets":118,"protocol":"tcp","service":"http"}'
{"label":"dos","confidence":1.0,"response_ms":12.54}
```

Ответ `200` и предсказание выданы; ошибка записи ушла в журнал приложения:

```
2026-11-22 16:17:48,915 WARNING nids.db: failed to write prediction log: connection
failed: connection to server at "127.0.0.1", port 5432 failed: could not receive data
from server: Software caused connection abort (0x00002745/10053)
Multiple connection attempts failed. All failures were:
- host: 'localhost', port: '5432', hostaddr: '::1': connection failed: ... server closed
  the connection unexpectedly
- host: 'localhost', port: '5432', hostaddr: '127.0.0.1': connection failed: could not
  receive data from server: Software caused connection abort
INFO:     127.0.0.1:50306 - "POST /predict HTTP/1.1" 200 OK
```

После `docker start nids-db` запись возобновилась без перезапуска сервиса.

### 2.11. Секреты и документация

`.env.example` содержит только имена переменных с пустыми значениями
(`DATABASE_URL`, `MODEL_DIR`, `MODEL_VERSION`), реальный `.env` перечислен в
`.gitignore`. `README.md` дополнен разделом про PostgreSQL: запуск `nids-db`,
применение миграций `001` и `002`, нагрузочная проверка и таблица переменных
окружения; разделы по ЛР №3 (Docker, размеры образов) сохранены.

## 3. Ответы на контрольные вопросы

**1. Чем `WHERE` отличается от `HAVING`? Пример, где без `HAVING` не обойтись.**

`WHERE` фильтрует строки до группировки, `HAVING` — уже сгруппированные строки, то
есть может ссылаться на агрегаты. Условие «сервисов, у которых не меньше 10
наблюдений» на уровне строк проверить нельзя — `COUNT(*)` появляется только после
`GROUP BY`:

```sql
SELECT service, COUNT(*) FROM predictions GROUP BY service HAVING COUNT(*) >= 10;
```

**2. Что даёт именованный том и что будет с базой без него?**

Именованный том — это хранилище, живущее независимо от контейнера: `docker rm` не
удаляет его данные, а новый контейнер с тем же `-v` видит прежние файлы. Без тома
каталог данных лежит в записываемом слое контейнера: при удалении контейнера
пропадают все файлы базы. Проверено в п. 2.3 — после пересоздания без `-v` таблица
пустая, с тем же томом вернулись все 503 строки. Дополнительно том отделяет данные
от образа: обновление `postgres:16-alpine` не затрагивает файлы базы.

**3. Почему параметры подключения берутся из окружения, а не пишутся в коде?**

Одна и та же сборка должна работать на машине разработчика, в тестовом и в
продуктивном окружении, где адреса и пароли разные. Захардкоженный пароль попадёт в
Git и останется в истории навсегда, даже после удаления строки; переменная
окружения позволяет передать секрет в момент запуска (или смонтировать из хранилища
секретов), не меняя код и не пересобирая образ.

**4. Почему поле с версией модели в журнале важнее остальных?**

Остальные поля описывают конкретное соединение и не меняются, а `model_version`
связывает запись с тем, какой моделью получено предсказание. Без него нельзя
сравнить поведение версий, невозможно отозвать результаты после отката модели и
непонятно, к каким данным применять переобучение: журнал превращается в набор
неатрибутированных чисел.

**5. Что показывает `EXPLAIN ANALYZE` и чем `Seq Scan` отличается от `Index Scan`?**

`EXPLAIN` показывает выбранный план, `ANALYZE` дополнительно выполняет запрос и
выдаёт фактические строки и время по каждому узлу, поэтому план можно сравнить с
оценкой планировщика. `Seq Scan` читает все страницы таблицы последовательно и
выгоден, когда нужна большая доля строк. `Index Scan` идёт по индексному дереву к
нужным строкам и читает только их (плюс обращения к таблице за остальными
колонками); он выгоден при выборке малой доли строк, особенно с `ORDER BY` по
индексированному полю — в п. 2.9 это дало `Index Scan Backward` без сортировки.

**6. Почему индекс не всегда ускоряет запрос?**

Индекс — дополнительная структура: её нужно обновлять при каждой вставке, изменении
и удалении, а поиск по ней сам стоит чтений. Если запрос всё равно читает большую
часть таблицы (агрегат без фильтра, `COUNT(*)` за час при 502 строках), дешевле
прочитать таблицу подряд, и планировщик оставляет `Seq Scan` — именно это видно в
первом плане п. 2.9. Индекс вреден и тогда, когда он не соответствует условию
(`WHERE` по выражению от колонки) или когда таблица мала и целиком помещается в
несколько страниц.

**7. Почему по журналу предсказаний нельзя напрямую посчитать точность модели?**

В журнале есть только ответ модели и её уверенность, но нет истинной метки:
правильный класс соединения в момент запроса неизвестен. Точность считается
сравнением прогноза с эталоном, поэтому дополнительно нужны размеченные данные —
отложенная тестовая выборка (как в `tests/`) либо последующая верификация инцидентов
и разметка экспертом, после которой журнал соединяется с фактическими метками.

**8. Чем миграция лучше `ALTER TABLE`, выполненного в консоли?**

`ALTER TABLE` в консоли — разовое действие, о котором знает только тот, кто его
выполнил: ни текста, ни порядка применения, ни возможности повторить на другой
машине. Миграция — версионированный файл в репозитории: она проходит код-ревью,
применяется тем же способом на любом окружении, попадает в историю Git и позволяет
поднять схему с нуля (в п. 2.4 так и было — миграция применена к пустому контейнеру
и создала рабочую таблицу).

## 4. Возникшие затруднения и способы их устранения

1. **Docker CLI не найден в PATH из git-bash.** `docker version` отвечал
   `command not found`, а прямой вызов по пути падал с
   `error getting credentials - exec: "docker-credential-desktop": executable file not found`.
   Решение: добавить каталог Docker Desktop в PATH перед вызовом —
   `export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"`. После этого
   `docker` нашёл и CLI, и helper для работы с учётными данными реестра.

2. **Порт 5432 мог быть занят локальным PostgreSQL.** Основной контейнер занимает
   `5432`, поэтому временный контейнер эксперимента с томом поднимался на `5433` —
   так опыт с «пустым» каталогом данных не конфликтует с рабочим.

3. **Счётчик строк в журнале не совпадал с числом запросов нагрузки.** В отчёте
   фигурируют 502 и 503 строки, хотя `load.py --n 500`. Причина: кроме нагрузки
   выполнялись одиночные `curl`-проверки `/predict` (в том числе при остановленной
   базе, когда запись не прошла). То есть журнал отражает все успешные записи, а не
   только нагрузочный прогон — это ожидаемо и полезно помнить при сверке чисел.

4. **`response_ms` при первом вызове оказался завышен (1410 мс).** В него попадала
   первая загрузка модели из `model.pkl` (ленивая инициализация в `get_model`).
   Такие выбросы видны и в перцентилях: `p99` в 1,8 раза выше медианы. Для чистоты
   измерений модель стоит загружать на старте приложения либо прогревать сервис
   одним запросом перед нагрузкой; в отчёте значения оставлены как есть, поскольку
   они отражают реальное поведение сервиса в момент замера.

5. **Секреты в коде.** Первая версия `db.py` содержала строку подключения по
   умолчанию с паролем. Она была удалена: теперь `DATABASE_URL` берётся только из
   окружения, а при отсутствии переменной `connect()` выбрасывает понятную ошибку
   `DATABASE_URL is not set`, которую перехватывает `log_safely`. Пароль остался
   только в командах запуска контейнера в README (учебное значение `devpassword`).

6. **Индекс не ускорил `COUNT(*)`.** Первая реакция — считать, что индекс «не
   работает». `EXPLAIN ANALYZE` показал, что планировщик сознательно оставил
   `Seq Scan`: при 502 строках дешевле прочитать таблицу. Эффект индекса проявился на
   запросе с `ORDER BY ... LIMIT` — там появился `Index Scan Backward`. Отсюда
   практический вывод: эффект индекса нужно проверять на запросе, для которого он
   создан, и на объёме, где он имеет смысл.

## 5. Ссылки

- Репозиторий: <https://github.com/Ro4hman/nids-service-BrilevRoman>
- Ветка с работой: <https://github.com/Ro4hman/nids-service-BrilevRoman/tree/feature/database>
- Миграции: `migrations/001_create_predictions.sql`, `migrations/002_index_created_at.sql`
- PR с отчётом: <https://github.com/Ro4hman/nids-service-BrilevRoman/pull/3>
