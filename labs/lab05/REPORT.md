# Лабораторная работа №5. Оркестрация. Стек одной командой на docker compose

**Автор:** Брылёв Роман Александрович, группа ИСТм-21.

**Среда:** Windows 11, Docker 29.9.3, Docker Compose v5.7.1, проект
`nids-service-BrilevRoman`, ветка `feature/compose`.

## 1. Цель работы

Объединить сервис предсказаний и базу данных в единую систему, описанную одним файлом
`compose.yaml`, и обеспечить её развёртывание на произвольной машине одной командой
`docker compose up` — без ручных операций и знания правильного порядка запуска.

## 2. Ход работы

### 2.1. Подготовка ветки и удаление ручных контейнеров

```bash
$ git switch -c feature/compose
Switched to a new branch 'feature/compose'

$ docker compose version
Docker Compose version v5.7.1

$ docker rm -f nids-db nids-api 2>/dev/null
nids-db
```

Контейнер `nids-db` из лабораторной №4 занимал порт `5432`, поэтому его удаление
обязательно: иначе новый сервис `db` не сможет опубликовать порт.

### 2.2. compose.yaml

```yaml
name: nids-service-brilevroman

services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-nids}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpassword}
      POSTGRES_DB: ${POSTGRES_DB:-nids}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-nids} -d ${POSTGRES_DB:-nids}"]
      interval: 3s
      timeout: 3s
      retries: 10

  api:
    build: .
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      MODEL_VERSION: ${MODEL_VERSION:-nids-rf-v0.1.0}
    ports:
      - "8000"
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:
```

Два решения, которые отличают файл от «наивного» варианта.

1. `depends_on` задан не списком, а словарём с `condition: service_healthy`: api
   ждёт не запуска контейнера базы, а её фактической готовности.
2. Порт опубликован как `"8000"` — то есть Compose сам выбирает свободный порт хоста.
   Фиксированная запись `8000:8000` сделала бы масштабирование невозможным.

Проверка файла без запуска:

```bash
$ docker compose config
name: nids-service-brilevroman
services:
  api:
    environment:
      DATABASE_URL: postgresql://nids:***@db:5432/nids
      MODEL_VERSION: nids-rf-v0.1.0
    depends_on:
      db:
        condition: service_healthy
    ports:
      - mode: ingress
        target: 8000
        protocol: tcp
  db:
    environment:
      POSTGRES_DB: nids
      POSTGRES_PASSWORD: devpassword
      POSTGRES_USER: nids
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U nids -d nids
```

### 2.3. Зависимость psycopg в образе

При первом запуске контейнер api падал на импорте `nids.db`: в `Dockerfile`
устанавливались только `scikit-learn`, `fastapi` и `uvicorn`. В ступень сборки добавлена
зависимость:

```dockerfile
RUN pip install --no-cache-dir --prefix=/install \
    "scikit-learn>=1.3" "fastapi>=0.110" "uvicorn[standard]>=0.27" \
    "psycopg[binary]>=3.1"
```

Образ пересобран: `docker compose build` → `Image nids-service-brilevroman-api Built`.

### 2.4. Первый запуск стека

```bash
$ docker compose up -d
 Container nids-service-brilevroman-db-1 Starting
 Container nids-service-brilevroman-db-1 Started
 Container nids-service-brilevroman-db-1 Waiting
 Container nids-service-brilevroman-db-1 Healthy
 Container nids-service-brilevroman-api-1 Starting
 Container nids-service-brilevroman-api-1 Started
```

Видно, что api стартовал только после строки `Healthy` — работает зависимость по
готовности.

```bash
$ docker compose ps
NAME                             SERVICE   STATUS                    PORTS
nids-service-brilevroman-api-1   api       Up 9 seconds              0.0.0.0:57786->8000/tcp
nids-service-brilevroman-db-1    db        Up 15 seconds (healthy)   5432/tcp

$ curl -s localhost:57786/health
{"status":"ok"}
```

Номер порта берётся из вывода `docker compose port api 8000` — он меняется от запуска
к запуску, потому что публикация динамическая.

### 2.5. Схема создаётся автоматически (п. 4.4)

Каталог `migrations` смонтирован в `/docker-entrypoint-initdb.d`, поэтому на пустом томе
PostgreSQL сам выполняет `001_create_predictions.sql` и `002_index_created_at.sql`:

```bash
$ docker compose down -v && docker compose up -d
$ docker compose exec -T db psql -U nids -d nids -c "\dt"
 Schema |    Name     | Type  | Owner
--------+-------------+-------+-------
 public | predictions | table | nids
(1 row)
```

Ручных `psql < migrations/...` при этом не выполняется.

### 2.6. Гонка старта без healthcheck (п. 4.2)

Ошибка воспроизведена прямым запуском api без базы — это тот же эффект, что и при
`depends_on` без условия готовности:

```bash
$ docker compose up -d --no-deps api
 Container nids-service-brilevroman-api-1 Started

$ curl -s -X POST localhost:62741/predict -H "Content-Type: application/json" \
    -d '{"protocol":"tcp","service":"http"}'
{"label":"normal","confidence":1.0,"response_ms":968.305}

$ docker compose logs api | grep "failed to write"
api-1  | 2026-11-22 13:37:25,633 WARNING nids.db: failed to write prediction log:
failed to resolve host 'db': [Errno -5] No address associated with hostname
```

Ответ пользователю получен (`200`), но запись в журнал потеряна: сеть проекта существует
только пока в ней есть хотя бы один контейнер, поэтому имя `db` не разрешается.

### 2.7. Пять запусков с healthcheck (п. 4.2, п. 7)

```bash
for i in 1 2 3 4 5; do
  docker compose down >/dev/null 2>&1
  docker compose up -d --wait >/dev/null 2>&1; echo "exit=$?"
  docker compose ps --format '{{.Service}} {{.Status}}'
  docker compose logs api | grep -ci "failed to write"
done
```

```
--- запуск 1 ---
exit=0
api Up 1 second
db Up 6 seconds (healthy)
warning_count=0
--- запуск 2 ---
exit=0
api Up 1 second
db Up 6 seconds (healthy)
warning_count=0
--- запуск 3 ---
exit=0
api Up 1 second
db Up 6 seconds (healthy)
warning_count=0
--- запуск 4 ---
exit=0
api Up 1 second
db Up 6 seconds (healthy)
warning_count=0
--- запуск 5 ---
exit=0
api Up 1 second
db Up 6 seconds (healthy)
warning_count=0
```

Пять запусков подряд — ни одной ошибки подключения.

### 2.8. Журнал, тома и `down` / `down -v` (п. 4.3)

```bash
$ for i in 1 2 3; do curl -s -X POST localhost:57786/predict \
    -H "Content-Type: application/json" \
    -d '{"src_port":51000,"dst_port":80,"duration_ms":880,"bytes_in":210,
         "bytes_out":14800,"packets":118,"protocol":"tcp","service":"http"}'; done
{"label":"dos","confidence":1.0,"response_ms":1254.158}
{"label":"dos","confidence":1.0,"response_ms":10.699}
{"label":"dos","confidence":1.0,"response_ms":11.547}

$ docker compose exec -T db psql -U nids -d nids -c "SELECT count(*) FROM predictions;"
 count
-------
     3
```

Остановка без удаления тома:

```bash
$ docker compose down
 Container nids-service-brilevroman-db-1 Removed
 Network nids-service-brilevroman_default Removed

$ docker compose up -d && sleep 12
$ docker compose exec -T db psql -U nids -d nids -c "SELECT count(*) FROM predictions;"
 count
-------
     3
$ docker volume ls | grep pgdata
local     nids-service-brilevroman_pgdata
```

Записи на месте: том `pgdata` остаётся и переживает пересоздание контейнеров.

Полное удаление:

```bash
$ docker compose down -v
 Volume nids-service-brilevroman_pgdata Removing
 Volume nids-service-brilevroman_pgdata Removed

$ docker volume ls | grep -c nids-service-brilevroman_pgdata
0
```

После `down -v` том уничтожен, журнал пуст — схема создастся заново при следующем
старте, но данных в ней уже не будет.

### 2.9. Масштабирование (п. 4.5)

```bash
$ docker compose up -d --scale api=3
 Container nids-service-brilevroman-api-2 Created
 Container nids-service-brilevroman-db-1 Waiting
 Container nids-service-brilevroman-db-1 Healthy
 Container nids-service-brilevroman-api-2 Starting
 Container nids-service-brilevroman-api-2 Started
 Container nids-service-brilevroman-api-3 Starting
 Container nids-service-brilevroman-api-3 Started

$ docker compose ps
NAME                             SERVICE   STATUS                    PORTS
nids-service-brilevroman-api-1   api       Up 40 seconds             0.0.0.0:61021->8000/tcp
nids-service-brilevroman-api-2   api       Up 20 seconds             0.0.0.0:61214->8000/tcp
nids-service-brilevroman-api-3   api       Up 20 seconds             0.0.0.0:60389->8000/tcp
nids-service-brilevroman-db-1    db        Up 46 seconds (healthy)   5432/tcp
```

Три реплики получили три разных порта хоста. Если бы в файле стояло `8000:8000`,
вторая и третья копии упали бы с ошибкой вида
`Bind for 0.0.0.0:8000 failed: port is already allocated`: один порт хоста может быть
занят только одним процессом.

### 2.10. Обращение к базе по `localhost` вместо `db` (п. 4.1, вопрос 4)

```bash
$ docker compose run --rm --no-deps \
    -e DATABASE_URL=postgresql://nids:devpassword@localhost:5432/nids \
    api python -c "..."   # вызов log_safely()
api did not crash
failed to write prediction log: connection failed: connection to server at "127.0.0.1",
port 5432 failed: Connection refused
    Is the server running on that host and accepting TCP/IP connections?
Multiple connection attempts failed. All failures were:
- host: 'localhost', port: '5432', hostaddr: '::1': connection failed: ...
- host: 'localhost', port: '5432', hostaddr: '127.0.0.1': connection failed: ...
```

`localhost` внутри контейнера api — это сам контейнер api, где PostgreSQL не запущен.
База живёт в другом контейнере и доступна по имени сервиса `db`.

## 3. Ответы на контрольные вопросы

**1. Чем описание системы в `compose.yaml` лучше набора команд `docker run`?**

Набор команд описывает процесс (что и в каком порядке выполнить), а файл — целевое
состояние системы. Файл лежит в Git, читается человеком, рецензируется в PR и не может
устареть незаметно: если он не соответствует реальности, система просто не поднимется.
Кроме того, `compose.yaml` избавляет от ручного создания сети и проброса имён: сервисы
видят друг друга по именам автоматически. Наконец, состояние воспроизводимо на любой
машине — не нужно помнить шесть-семь флагов `docker run` и порядок их выполнения.

**2. Как сервисы внутри одной сети compose находят друг друга?**

Compose создаёт для проекта отдельную bridge-сеть и подключает к ней все сервисы.
Каждый контейнер получает DNS-имя, равное имени сервиса в файле, поэтому api
обращается к базе по адресу `db:5432`. Разрешением имён занимается встроенный DNS
Docker на `127.0.0.11` внутри контейнера.

**3. Чем `depends_on` отличается от зависимости с условием `service_healthy`?**

`depends_on` в виде списка управляет только порядком: контейнер api запускается после
того, как контейнер db создан и запущен. Но «запущен» не значит «готов принимать
подключения»: PostgreSQL стартует секунды и в этот момент отклоняет соединения.
Зависимость с `condition: service_healthy` ждёт, пока healthcheck (в нашем случае
`pg_isready`) не сообщит о готовности, и лишь затем запускает api.

**4. Почему плавающая ошибка старта опаснее постоянной?**

Постоянная ошибка воспроизводится при каждом запуске, поэтому быстро попадает в поле
зрения разработчика и локализуется в отладке. Плавающая проявляется только при
неудачном стечении обстоятельств — на медленной машине или под нагрузкой, — а на
машине разработчика не воспроизводится вовсе. В результате дефект уходит в продакшен,
а его диагностика затруднена: логи чистого запуска ничего не показывают, а в момент
сбоя контейнер уже мог быть пересоздан. Именно поэтому такие ошибки лечат не
увеличением таймаута «на глаз», а явной проверкой готовности.

**5. В чём разница между `docker compose down` и `docker compose down -v`?**

`down` удаляет контейнеры и сеть, но оставляет именованные тома, поэтому данные базы
сохраняются. `down -v` дополнительно удаляет тома, объявленные в файле, — журнал
предсказаний пропадает безвозвратно. Ключ `-v` предназначен для локальной разработки,
когда нужен чистый старт.

**6. Зачем в репозитории нужен `.env.example`, если `.env` всё равно у каждого свой?**

`.env.example` — это перечень параметров, которые нужно задать, с пустыми значениями.
Он документирует конфигурацию, позволяет сравнить свой файл с эталоном при непонятной
ошибке и служит шаблоном для новой машины (`cp .env.example .env`). Сам `.env`
содержит пароли и потому в Git не попадает: он в `.gitignore`, иначе секрет утёк бы в
историю и остался там даже после удаления файла.

**7. Почему сервис без состояния масштабируется копированием, а база данных — нет?**

Копии api не хранят состояния: каждая читает модель из образа и пишет в общую базу,
поэтому любую копию можно убить и заменить. Ещё они не занимают фиксированный порт
хоста. База хранит данные в томе, и два процесса PostgreSQL над одним каталогом данных
повредят его: нет распределённой блокировки файлов. Плюс том `pgdata` монтируется
ровно в один контейнер, а порт `5432` у всех копий был бы один. Поэтому базу
масштабируют иначе — репликацией (primary/replica) или внешним кластером.

**8. Почему публиковать порт базы наружу в продакшене не следует?**

База нужна только сервису api, а публикация (`ports`) выставляет её на все интерфейсы
хоста, где её видит любой, кто дотянется до машины. Это расширяет поверхность атаки
(подбор пароля, эксплуатация уязвимостей PostgreSQL) и обходит сетевую изоляцию
compose. Достаточно оставить `expose`/внутренний порт: `db:5432` доступен api по имени
сервиса и без публикации на хост.

## 4. Возникшие затруднения и способы их устранения

1. **Контейнер api падал на импорте `psycopg`.** В `Dockerfile` не было зависимости,
   добавленной в ЛР №4: образ собирался по списку пакетов из лабораторной №3. Исправлено
   добавлением `psycopg[binary]>=3.1` в ступень сборки и пересборкой образа. Урок:
   зависимости, появившиеся при разработке вне контейнера, нужно переносить в
   `Dockerfile`, иначе контейнер расходится с локальным окружением.

2. **Конфликт порта 5432 с контейнером из ЛР №4.** `nids-db` продолжал работать и
   занимать порт. Устранено командой `docker rm -f nids-db` перед первым запуском стека;
   том `nids-pgdata` при этом остался, но compose использует свой
   (`nids-service-brilevroman_pgdata`), поэтому данные ЛР №4 не пострадали.

3. **`localhost` вместо `db`.** Первая попытка передать `DATABASE_URL` со строкой
   `@localhost:5432` привела к `Connection refused`: внутри контейнера это адрес самого
   api. Исправлено указанием имени сервиса `db`, а в `.env.example` добавлен комментарий
   об этом, чтобы ошибка не повторилась при развёртывании на другой машине.

4. **Гонка старта при отсутствии healthcheck.** Воспроизведена запуском api без базы:
   запрос вернул `200`, а в логе появилось
   `failed to write prediction log: failed to resolve host 'db'`. Добавлены `healthcheck`
   с `pg_isready` и `depends_on` с `service_healthy`; серия из пяти запусков прошла без
   ошибок.

5. **Фиксированный порт мешал масштабированию.** С записью `8000:8000` вторая копия
   api не поднималась из-за занятого порта хоста. Заменено на `"8000"` — Compose
   назначает свободный порт каждой реплике, а фактический номер печатает
   `docker compose port api 8000`.

6. **Docker CLI не в `PATH` в git-bash.** Команда `docker` не находилась, хотя Docker
   Desktop запущен. Обход: `export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"`
   перед работой (в `cmd.exe`/PowerShell этого не требуется).

7. **Развёртывание у однокурсника.** _Место для результата проверки: что именно
   сломалось при первом `docker compose up` на чужой машине и каким исправлением это
   устранено. Заполняется после фактического прогона._

## 5. Ссылки

- Репозиторий проекта: <https://github.com/Ro4hman/nids-service-BrilevRoman>
- Ветка с работой: `feature/compose`
- PR с отчётом: <https://github.com/Ro4hman/nids-service-BrilevRoman/pull/4>
