# Лабораторная работа №6. Непрерывная интеграция и доставка. Пайплайн в GitHub Actions

**Автор:** Бырлёв Роман Александрович, группа ИСТм-21.
**Репозиторий:** <https://github.com/Ro4hman/nids-service-BrilevRoman>

## 1. Цель работы

Настроить автоматическую проверку и сборку проекта в GitHub Actions: на каждое изменение
выполняются статический анализ и тесты, собирается и публикуется образ, а слияние в `main`
при неуспешных проверках блокируется. Отдельная цель — тест на порог качества модели,
прерывающий сборку при ухудшении метрики F1.

## 2. Ход работы

### 2.1. Подготовка и локальная проверка

```bash
git switch -c feature/ci
mkdir -p .github/workflows
python -m pip install -e ".[dev]" ruff
ruff check .
pytest -q
```

Первый прогон линтера нашёл два замечания в `src/app.py`:

```
I001 [*] Import block is un-sorted or un-formatted
 --> src\app.py:3:1
UP031 Use format specifiers instead of percent format
  --> src\app.py:26:15
Found 2 errors.
```

Исправлено: импорты отсортированы, `%`-формат заменён на f-строку. Правила закреплены
в `pyproject.toml`, чтобы локальная и серверная проверки совпадали:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

С расширенным набором правил обнаружились ещё три замечания — перенос длинных
выражений в `data/make_dataset.py` (`E501`) и неиспользуемая переменная цикла
в `scripts/load.py` (`B007`). После правок:

```
$ ruff check .
All checks passed!
$ pytest -q
8 passed, 1 warning in 1.42s
```

### 2.2. Workflow CI

`.github/workflows/ci.yml`: job `test` на `push` в `main` и на любой `pull_request`,
job `build` с `needs: test`.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  packages: write

jobs:
  test:
    name: lint and test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]" ruff

      - name: Lint
        run: ruff check .

      - name: Test
        run: pytest -q
```

### 2.3. Замер времени job-а до и после кэширования

Кэш `pip` включается параметром `cache: pip` в `actions/setup-python` с указанием
файла зависимостей `cache-dependency-path: pyproject.toml`. Фактические длительности
job-а `lint and test` из API GitHub Actions:

| Прогон | Коммит | Длительность `lint and test` |
|---|---|---|
| #2 | `b82de51` | 28 s (первый прогон, кэш пуст) |
| #3 | `2d64911` | 36 s |
| #4 | `7654651` | 30 s |
| #5 | `4ec96f1` | 27 s |

Выигрыш от кэша невелик и нестабилен: установка небольшого набора пакетов
(`scikit-learn`, `fastapi`, `uvicorn`, `psycopg`, `pytest`, `httpx`, `ruff`) занимает
десяток секунд, а основное время уходит на запуск runner-а, checkout и сам прогон
pytest. Кэш всё же полезен: он убирает сетевые обращения к PyPI и делает время
прогона предсказуемым.

### 2.4. Тест порога качества модели

`tests/test_model_quality.py` читает `artifacts/metadata.json` и сверяет метрики
с порогами:

```python
F1_MIN = 0.85
ACC_MIN = 0.90
...
assert f1 >= F1_MIN, f"качество модели упало: f1_macro={f1} < порога {F1_MIN}"
```

Проверка действенности: временно испорчена подготовка признаков — в `nids/__init__.py`
четыре объёмных признака (`duration_ms`, `bytes_in`, `bytes_out`, `packets`)
заменены константой `0.0`, модель переобучена.

```
$ python -m nids.train
  "accuracy": 0.592,
  "f1_macro": 0.2083

$ pytest -q
E       AssertionError: качество модели упало: f1_macro=0.2083 < порога 0.85
E       AssertionError: качество модели упало: accuracy=0.592 < порога 0.90
E       assert 0.592 >= 0.8
FAILED tests/test_model_quality.py::test_f1_meets_threshold
FAILED tests/test_model_quality.py::test_accuracy_meets_threshold
FAILED tests/test_train.py::test_metadata_metrics
3 failed, 5 passed
```

Упали ровно те три проверки, которые смотрят на метрики обученной модели.
Прошли контрактные тесты API (`/health`, форма ответа `/predict`) и проверки датасета:
они не зависят от качества модели — сервис по-прежнему отвечает корректной структурой,
просто предсказания становятся неверными. Это и есть разграничение «код исправен» /
«система выполняет назначение». После восстановления `encode()`: `8 passed`,
`f1_macro = 0.9557`, `accuracy = 0.992`.

### 2.5. Сборка, публикация и сканирование образа

```yaml
  build:
    name: build and publish image
    needs: test
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v7

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build image
        run: |
          IMAGE=nids-service
          docker build -t "$IMAGE:${{ github.sha }}" .

      - name: Scan image with Trivy
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: nids-service:${{ github.sha }}
          format: table
          output: trivy-report.txt
          exit-code: "1"
          ignore-unfixed: true
          severity: HIGH,CRITICAL

      - name: Tag and push image
        run: |
          IMAGE=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/nids-service
          docker tag "nids-service:${{ github.sha }}" "$IMAGE:${{ github.sha }}"
          docker tag "nids-service:${{ github.sha }}" "$IMAGE:latest"
          docker push "$IMAGE:${{ github.sha }}"
          docker push "$IMAGE:latest"
```

Сканирование выполняется по локально собранному тегу: в реестр образ попадает только
после успешного скана, поэтому ссылку `ghcr.io/...` на этом шаге использовать нельзя —
образа там ещё нет.

Сводка Trivy. Первый прогон нашёл уязвимость в базовом слое:

```
nids-service (debian 13.7)
Total: 1 (HIGH: 1, CRITICAL: 0)
zlib1g  CVE-2026-85091  HIGH  fixed  1:1.3.dfsg+really1.3.1-1+b1
        → 1:1.3.dfsg+really1.3.1-1+deb13u1
        zlib: Heap buffer overflow in gz_vacate() allows arbitrary code execution
```

Сканирование пакетов Python дало нули по всем зависимостям. После обновления пакетов
базового образа в рантайм-слое `Dockerfile`:

```dockerfile
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
```

```
$ docker run --rm -v //var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:latest image --severity HIGH,CRITICAL \
    --ignore-unfixed --exit-code 1 nids-scan-test2
nids-scan-test2 (debian 13.8)
Total: 0 (HIGH: 0, CRITICAL: 0)
```

Итоговая сводка: **0 уязвимостей уровня HIGH, 0 уровня CRITICAL**; полный отчёт
сохраняется артефактом `trivy-report` (`trivy-report.txt`) в каждом прогоне.

Проверка образа локально:

```bash
$ docker build -t nids-service:local .
$ docker run -d --name nids-check -p 8000:8000 nids-service:local
$ curl -s localhost:8000/health
{"status":"ok"}
```

### 2.6. Хронология прогонов и защита ветки

| Прогон | Коммит | `lint and test` | `build and publish image` | Причина отказа |
|---|---|---|---|---|
| #1 | `eb2f7af` | 28 s | — | `aquasecurity/trivy-action@0.28.0` не существует |
| #2 | `b82de51` | 28 s | 3 s | то же (после слияния PR #6) |
| #3 | `2d64911` | 36 s | 7 s | `Build image`: заглавные буквы в имени образа GHCR |
| #4 | `7654651` | 30 s | 48 s | `Scan image with Trivy`: HIGH `zlib1g` в базовом слое |
| #5 | `4ec96f1` | 27 s | 58 s | `Tag and push image`: двухуровневый путь `ghcr.io/owner/repo/image` |

На прогоне #5 шаги `Build image`, `Scan image with Trivy` и `Upload Trivy report`
завершились успешно — то есть сборка и сканирование настроены верно, отказ остался
только на публикации. Прямой push исправления в `main` отклоняется:

```
$ git push
! [remote rejected] main -> main (push declined due to repository rule violations)
```

Это подтверждает, что правило защиты `main` включено и работает: изменения проходят
только через ветку и Pull Request. Исправление пути к образу вынесено в ветку
`fix/ci-ghcr-image`, слияние — через PR.

## 3. Ответы на контрольные вопросы

**1. Почему сборка на чистом runner-е заслуживает большего доверия, чем на машине
разработчика?**
Чистый runner не содержит ничего, кроме базового образа и того, что явно описано
в workflow. Если проект собирается там, значит все зависимости объявлены, а не
подхвачены случайно из локального окружения. На машине разработчика могут быть
установлены пакеты, сохранённые артефакты, изменённые переменные окружения, старая
версия интерпретатора — сборка пройдёт, а у коллеги или на сервере упадёт.
Дополнительно runner воспроизводим: один и тот же коммит даёт один и тот же результат
у всех участников.

**2. Что делает `needs` и что может произойти без него?**
`needs` задаёт зависимость между job-ами: зависимый job стартует только после
успешного завершения указанного. Без него job-ы идут параллельно, и `build`
начнёт собирать и публиковать образ одновременно с тестами. Тогда в реестр может
попасть образ из кода, который не прошёл линтер или уронил тесты, — то есть
публикуется заведомо нерабочая версия. Кроме того, при падении тестов сборка
всё равно выполнится и потратит минуты runner-а впустую.

**3. Почему контрактный тест проверяет форму ответа, а не конкретное предсказание?**
Предсказание — величина, зависящая от модели, гиперпараметров, seed-а и данных;
после любого переобучения оно законно изменится. Тест, ожидающий конкретное значение,
начал бы падать не из-за ошибки в коде, а из-за нормального изменения модели, —
и его быстро отключили бы как «постоянно красный». Форма же ответа (наличие полей,
типы, коды HTTP, границы вероятности) — это контракт API, он меняться не должен.
Качество предсказаний контролируется отдельно, тестом порога метрики.

**4. Какую ошибку ловит тест на порог метрики? Приведите пример изменения, которое
пройдёт все остальные тесты и провалит этот.**
Он ловит деградацию качества модели при формально исправном коде. Пример из работы:
из подготовки признаков исключены объёмные признаки (`duration_ms`, `bytes_in`,
`bytes_out`, `packets`) — заменены константой. Код исполняется без исключений,
API отвечает правильной структурой, все контрактные тесты зелёные, но `f1_macro`
падает с `0.9557` до `0.2083`, и сборка останавливается.

**5. Как выбрать значение порога? Чем плох слишком высокий и слишком низкий порог?**
Порог берут заметно ниже достигнутого качества, но выше уровня случайного угадывания
и требований задачи. Слишком высокий порог (например, `0.99` при фактических `0.9557`)
делает сборку нестабильной: любое законное колебание метрики, смена seed-а или
добавление данных ломают её, и на красные прогоны перестают реагировать — тест
обесценивается. Слишком низкий (например, `0.5` при четырёх классах) пропускает
реальную деградацию: модель, потерявшая половину информативных признаков, всё ещё
проходит проверку.

**6. Чем `secrets.GITHUB_TOKEN` лучше токена, созданного вручную?**
Он выдаётся платформой на время одного запуска и перестаёт действовать сразу после
его завершения. Его не нужно создавать, хранить, ротировать и передавать коллегам;
права ограничены блоком `permissions` workflow. Утечка долгоживущего ручного токена
опасна до момента отзыва — а отзывают его, как правило, уже после инцидента.

**7. Почему образ тегируют хешем коммита?**
Хеш однозначно связывает образ с состоянием исходного кода, из которого он собран,
и никогда не переиспользуется для другого содержимого. Тег `latest` перезаписывается
каждой сборкой: невозможно сказать, какой код в нём находится сейчас, нельзя
воспроизвести ранее работавшую версию и откатиться на неё, а разные узлы кластера
могут одновременно держать разные образы под одним именем. При использовании `latest`
теряется воспроизводимость и возможность точного отката.

**8. Почему CI без защиты основной ветки почти не влияет на качество?**
Потому что результат проверок ни к чему не обязывает: красный прогон легко
проигнорировать и влить изменения напрямую. CI превращается в информационную
ленту, которую перестают читать. Только обязательный статус-чек делает проверку
условием слияния, и тогда ошибку физически нельзя протащить в `main`.

## 4. Возникшие затруднения и способы их устранения

1. **`aquasecurity/trivy-action@0.28.0` не существует.** Прогоны #1 и #2 падали на
   разборе workflow: `Unable to resolve action aquasecurity/trivy-action@0.28.0,
   unable to find version 0.28.0`. Причина — тег без префикса `v` и устаревший
   номер: в репозитории действия версии помечены как `v0.28.0`, `v0.36.0` и т. д.
   Решение: список тегов получен через API GitHub и указан актуальный
   `aquasecurity/trivy-action@v0.36.0`.

2. **Предупреждение об устаревании Node.js 20.** GitHub выводил: используемые
   действия (`actions/checkout@v4`, `actions/setup-python@v5`) запускаются на
   Node.js 20, поддержка которого прекращается, и платформа принудительно
   переводит их на Node.js 24. Решение: версии действий подняты до актуальных
   (`checkout@v7`, `setup-python@v7`, `upload-artifact@v7`,
   `docker/login-action@v3`), предупреждение исчезло.

3. **Заглавные буквы в имени образа GHCR.** Прогон #3 упал на шаге `Build image`:
   реестр GHCR принимает только имена в нижнем регистре, а
   `${{ github.repository }}` содержит `Ro4hman` и `BrilevRoman`. Решение:
   подстановка bash `${GITHUB_REPOSITORY,,}`. Локальная сборка того же `Dockerfile`
   проходила, поэтому причина искалась именно в имени тега.

4. **Двухуровневый путь к образу.** Прогон #5: сборка и скан прошли, но
   `Tag and push image` упал. `ghcr.io/${{ github.repository }}/nids-service`
   разворачивается в `ghcr.io/ro4hman/nids-service-brilevroman/nids-service` —
   два уровня после владельца, что для GHCR недопустимо. Решение:
   `ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/nids-service`, то есть
   `ghcr.io/ro4hman/nids-service`.

5. **Сканирование образа до его публикации.** Первоначально `image-ref` указывал на
   `ghcr.io/...:${{ github.sha }}`, хотя на этом шаге образ ещё не запушен:
   Trivy нечего было сканировать. Решение: сканируется локальный тег
   `nids-service:${{ github.sha }}`, а переименование под GHCR и `docker push`
   выполняются после успешного скана.

6. **Уязвимость HIGH в базовом слое.** Trivy нашёл `zlib1g CVE-2026-85091`
   (`HIGH`, исправление доступно) в `python:3.12-slim` (debian 13.7), из-за чего
   сборка падала с `exit-code: 1`. Решение: в рантайм-слое добавлен
   `apt-get update && apt-get upgrade -y --no-install-recommends`; базовый слой
   обновился до debian 13.8, итог сканирования — `0 HIGH, 0 CRITICAL`.

7. **Push в `main` отклоняется.** После включения защиты ветки прямая отправка
   возвращает `push declined due to repository rule violations`. Решение:
   изменения оформляются в отдельной ветке (`fix/ci-ghcr-image`) и вливаются
   через Pull Request с обязательным зелёным статус-чеком.

## 5. Ссылки

- Репозиторий проекта: <https://github.com/Ro4hman/nids-service-BrilevRoman>
- Workflow: <https://github.com/Ro4hman/nids-service-BrilevRoman/blob/main/.github/workflows/ci.yml>
- Прогоны CI: <https://github.com/Ro4hman/nids-service-BrilevRoman/actions/workflows/ci.yml>
- Ветка с исправлением публикации образа:
  <https://github.com/Ro4hman/nids-service-BrilevRoman/tree/fix/ci-ghcr-image>
- PR с отчётом: _заполняется после создания Pull Request_
