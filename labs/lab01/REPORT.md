# Лабораторная работа №1. Система контроля версий Git. Репозиторий сквозного проекта

**Автор:** Брылёв Роман Александрович, группа ИСТм-21
**Репозиторий:** <https://github.com/Ro4hman/nids-service-BrilevRoman>

## 1. Цель работы

Освоить базовый рабочий процесс Git (индекс, коммит, ветвление, слияние, разрешение
конфликтов, отмена изменений) и организовать в GitHub репозиторий сквозного проекта
с осмысленной историей и оформлением изменений через Pull Request.

## 2. Ход работы

### 2.1. Окружение и первичная настройка

Работа выполнялась в Windows без WSL: Git 2.56.1 (MSYS2/ucrt64) и Python 3.14.9 из
обычной командной строки bash. Репозиторий был создан пустым, поэтому шаблон сквозного
проекта пришлось заменить минимальным скелетом (`src/app.py` — HTTP-сервис на
стандартной библиотеке с эндпоинтом `GET /health`).

```bash
$ git --version
git version 2.56.1.windows.1

$ git config --global user.name "Byrlev Roman"
$ git config --global user.email "ro4hman@users.noreply.github.com"
$ git config --global init.defaultBranch main
$ git config --global core.autocrlf input

$ git config --global --list | grep -E 'user|branch|autocrlf'
user.name=Byrlev Roman
user.email=ro4hman@users.noreply.github.com
init.defaultbranch=main
core.autocrlf=input

$ git clone git@github.com:Ro4hman/nids-service-BrilevRoman.git
warning: You appear to have cloned an empty repository.
```

Доступ к GitHub настроен по SSH-ключу ed25519:

```bash
$ ssh -T git@github.com
Hi Ro4hman! You've successfully authenticated, but GitHub does not provide shell access.
```

`core.autocrlf=input` выбран осознанно: в рабочем каталоге Windows файлы имеют CRLF,
а в репозиторий попадает LF, поэтому история не «дёргается» при переключении между
машинами с разными переводами строк.

### 2.2. Индекс и первый коммит (задание 4.2)

Разница между `git status` до и после `git add` — это переход файла из состояния
*untracked* (Git о нём ничего не знает) в состояние *staged* (содержимое записано
в индекс, то есть подготовлено к следующему коммиту). Сам коммит фиксирует именно
содержимое индекса, а не текущее состояние рабочего каталога.

```bash
$ git status
Untracked files:
	README.md
	src/

$ git add README.md src/app.py
$ git status
Changes to be committed:
	new file:   README.md
	new file:   src/app.py

$ git commit -m "chore: add project skeleton"
[main (root-commit) 3af0412] chore: add project skeleton
 2 files changed, 46 insertions(+)
 create mode 100644 README.md
 create mode 100644 src/app.py
```

Сведения об авторе добавлены отдельным коммитом. `AUTHOR.md` до `git add` отображается
как untracked, после — как «new file» в разделе изменений, подготовленных к коммиту:

```bash
$ git status
Untracked files:
	AUTHOR.md

$ git add AUTHOR.md
$ git status
Changes to be committed:
	new file:   AUTHOR.md

$ git diff --cached --stat
 AUTHOR.md | 7 +++++++
 1 file changed, 7 insertions(+)

$ git commit -m "docs: add author info"
[main d855ca9] docs: add author info
 1 file changed, 7 insertions(+)
 create mode 100644 AUTHOR.md
```

### 2.3. Ветка feature/readme и Pull Request (задание 4.3)

Документация дополнялась тремя независимыми по смыслу коммитами: назначение сервиса,
инструкция по запуску, структура проекта и таблица HTTP API. Ветка отправлена в origin
для PR в `main`.

```bash
$ git switch -c feature/readme
Switched to a new branch 'feature/readme'

$ git commit -m "docs: describe project purpose"
[feature/readme 621c80d] docs: describe project purpose
 1 file changed, 10 insertions(+), 3 deletions(-)

$ git commit -m "docs: add run instructions"
[feature/readme a00c2fa] docs: add run instructions
 1 file changed, 17 insertions(+)

$ git commit -m "docs: add project structure and API table"
[feature/readme 5d0a0e0] docs: add project structure and API table
 1 file changed, 18 insertions(+)

$ git push -u origin feature/readme
 * [new branch]      feature/readme -> feature/readme
```

Позже, после слияния экспериментальных веток, `main` был подтянут в `feature/readme`
(`git merge origin/main`), чтобы PR сливался без конфликтов.

### 2.4. Ветвление и конфликт слияния (задание 4.4)

От `main` созданы две ветки, в каждой изменена одна и та же первая строка `README.md`.
Так как правки касаются одной строки, автоматическое слияние невозможно.

```bash
$ git switch -c exp/alpha
$ sed -i '1s/.*/# nids-service — сборка Alpha (экспериментальная ветка)/' README.md
$ git commit -am "exp: alpha build title"
[exp/alpha aae31e8] exp: alpha build title

$ git switch main && git switch -c exp/beta
$ sed -i '1s/.*/# NIDS Service — демонстрационный стенд Beta/' README.md
$ git commit -am "exp: beta build title"
[exp/beta f81497c] exp: beta build title

$ git switch exp/alpha
$ git merge exp/beta
Auto-merging README.md
CONFLICT (content): Merge conflict in README.md
Automatic merge failed; fix conflicts and then commit the result.

$ git status
You have unmerged paths.
  (fix conflicts and run "git commit")
Unmerged paths:
	both modified:   README.md
```

Файл с маркерами конфликта:

```text
<<<<<<< HEAD
# nids-service — сборка Alpha (экспериментальная ветка)
=======
# NIDS Service — демонстрационный стенд Beta
>>>>>>> exp/beta
```

Смысл маркеров: `<<<<<<< HEAD` открывает блок с версией **текущей ветки** (той, в которую
выполняется слияние, — `exp/alpha`); `=======` разделяет конфликтующие варианты;
`>>>>>>> exp/beta` закрывает блок с версией **вливаемой ветки**. Текст вне маркеров
конфликтом не является и сохраняется автоматически.

Разрешение выполнено вручную: обе формулировки объединены в одну строку, маркеры удалены,
результат зафиксирован merge-коммитом, затем слит в `main`, а отработавшие ветки удалены
локально и на сервере.

```bash
$ git add README.md
$ git commit -m "merge: слить exp/beta в exp/alpha, разрешить конфликт заголовка"
[exp/alpha f583a25] merge: слить exp/beta в exp/alpha, разрешить конфликт заголовка

$ git switch main
$ git merge --no-ff exp/alpha -m "merge: принять результат разрешения конфликта Alpha/Beta"

$ git branch -d exp/alpha exp/beta
Deleted branch exp/alpha (was f583a25).
Deleted branch exp/beta (was f81497c).

$ git push origin --delete exp/alpha exp/beta
 - [deleted]         exp/alpha
 - [deleted]         exp/beta
```

### 2.5. `.gitignore` и уже отслеживаемый файл (задание 4.5)

Созданы типичные артефакты: бинарь модели `model.pkl`, файл секретов `.env`
(`DB_PASSWORD=secret`) и каталог кэша `__pycache__/`. Чтобы проверить поведение для
**уже закоммиченного** файла, `model.pkl` сначала был закоммичен, и только потом внесён
в `.gitignore`.

```bash
$ git add model.pkl && git commit -m "feat: add trained model artifact"
[main 8a56666] feat: add trained model artifact

$ cat .gitignore
# артефакты моделей
*.pkl

# секреты и локальная конфигурация
.env

# кэш интерпретатора Python
__pycache__/
*.py[cod]

$ git commit -am "chore: add .gitignore for artifacts and secrets"
[main 638e820] chore: add .gitignore for artifacts and secrets
```

Проверка показала: `.gitignore` действует только на файлы, которые Git ещё не отслеживает.

```bash
$ git status --ignored --short
!! .env
!! __pycache__/

$ git ls-files | grep pkl
model.pkl

$ printf 'new-bytes\n' >> model.pkl
$ git status --short
 M model.pkl
```

То есть `model.pkl` остался в индексе, а его изменения продолжают попадать в `git status`.
Чтобы правило заработало, файл нужно снять с отслеживания (сам файл на диске остаётся):

```bash
$ git rm --cached model.pkl
$ git commit -m "chore: stop tracking model.pkl (артефакт, игнорируется)"
$ git ls-files
.gitignore
AUTHOR.md
README.md
src/app.py
```

### 2.6. Отмена ошибочного коммита: `git revert` (задание 4.6)

В `main` намеренно сделан «плохой» коммит, удаляющий входной файл сервиса. Ошибка
проявляется сразу при запуске:

```bash
$ git rm src/app.py
$ git commit -m "chore: remove obsolete entrypoint"
[main 067ba43] chore: remove obsolete entrypoint
 1 file changed, 41 deletions(-)
 delete mode 100644 src/app.py

$ python src/app.py
python.exe: can't open file '...\\nids-service-BrilevRoman\\src\\app.py': [Errno 2] No such file or directory
```

Коммит уже отправлен в origin, поэтому история не переписывается — создаётся обратный
коммит:

```bash
$ git revert HEAD --no-edit
[main ed8171a] Revert "chore: remove obsolete entrypoint"
 1 file changed, 41 insertions(+)
 create mode 100644 src/app.py

$ git push origin main
$ python src/app.py &
$ curl -s http://127.0.0.1:8000/health
{"status": "ok"}
```

**`git revert` против `git reset --hard`.** `revert` не удаляет коммит из истории,
а добавляет новый, отменяющий его изменения; история остаётся линейной и общей для всех,
кто уже получил эти коммиты. `reset --hard` передвигает указатель ветки назад и стирает
изменения из рабочего каталога и индекса: коммит исчезает из ветки, будто его не было.
Для уже отправленной истории это опасно: у коллег останутся «исчезнувшие» коммиты,
их локальные ветки разойдутся с сервером, а следующий `push` потребует `--force`,
который перезапишет чужую работу. `reset --hard` уместен только для локальных,
ещё не опубликованных коммитов.

### 2.7. Итоговая история

```text
$ git log --oneline --graph --all
* ed8171a Revert "chore: remove obsolete entrypoint"
* 067ba43 chore: remove obsolete entrypoint
* 1949e6c chore: stop tracking model.pkl (артефакт, игнорируется)
* 638e820 chore: add .gitignore for artifacts and secrets
* 8a56666 feat: add trained model artifact
* e1f93f9 fix: единственный заголовок README после слияния
*   85a36a0 merge: принять результат разрешения конфликта Alpha/Beta
...
* 3af0412 chore: add project skeleton
```

## 3. Ответы на контрольные вопросы

**1. Чем коммит отличается от «сохранённой версии файла»? Что хранится в коммите?**
Коммит — это снимок **всего дерева проекта** в некоторый момент, а не версия отдельного
файла. Внутри хранятся: хеш корневого дерева (дерево каталогов и блобов с содержимым
файлов), хеш родительского коммита (или нескольких — для слияния), автор и дата авторства,
коммиттер и дата коммита, сообщение. Сам коммит идентифицируется SHA-хешем своего
содержимого, поэтому любые изменения в истории меняют хеши всех последующих коммитов.
Файлы при этом не дублируются: неизменённые блобы переиспользуются по хешу.

**2. Зачем нужен индекс? Ситуация, где без него нельзя.**
Индекс (staging area) — это промежуточный снимок, из которого формируется следующий
коммит; он позволяет собрать коммит из **части** изменений рабочего каталога. Пример:
в `README.md` одновременно исправлена опечатка и добавлен большой новый раздел, а также
изменены три исходных файла, относящиеся к другой задаче. Нужен коммит только с
исправлением опечатки: `git add -p README.md` (или `git add` конкретных файлов) отправляет
в индекс лишь нужный хунк, а остальное остаётся в рабочем каталоге. Без промежуточной
области любой коммит захватывал бы всё изменённое сразу — нельзя было бы разделить работу
на логически независимые коммиты и пришлось бы временно откатывать лишние правки.

**3. Почему создание ветки мгновенно независимо от размера проекта?**
Ветка в Git — это просто файл в `.git/refs/heads/`, содержащий 40-символьный SHA коммита
(на практике — одна строка в `packed-refs`). Создание ветки записывает этот указатель,
никакие файлы проекта не копируются. Поэтому время операции O(1) и не зависит ни от
числа файлов, ни от их размера, в отличие от систем, где ветка — отдельный каталог.

**4. `git add file.txt`, затем правка файла, затем `git commit` — какая версия попадёт?**
Попадёт та версия, которая была **на момент `git add`**, потому что коммит строится из
индекса, а более поздняя правка осталась только в рабочем каталоге. После коммита
`git status` покажет файл как изменённый (`modified`), и его нужно добавить повторно.
Именно поэтому привычка «сначала add, потом ещё поправил» приводит к коммитам без
последних изменений.

**5. Почему датасет на 3 ГБ не хранить в Git? Конкретные последствия.**
Git хранит полную историю и рассчитан на текстовые файлы: каждая версия бинаря сохраняется
целиком, дельта-сжатие для бинарных данных почти не работает. Последствия: (1) репозиторий
раздувается — 10 версий датасета дают ~30 ГБ в `.git`; (2) `git clone`/`git fetch`
становятся неприемлемо долгими для всех участников; (3) операции, обходящие историю
(`git log`, `git blame`, переключение веток, CI-чекаут), замедляются; (4) GitHub отклоняет
файлы больше 100 МБ и предупреждает начиная с 50 МБ; (5) удаление файла новым коммитом
не уменьшает размер репозитория — блоб остаётся в истории, чистить приходится
`filter-repo` с перезаписью истории. Правильный путь — `.gitignore` для датасетов,
хранение артефактов в DVC / Git LFS / объектном хранилище, а в Git держать только
манифест и скрипт загрузки.

**6. Что означают маркеры `<<<<<<<`, `=======`, `>>>>>>>`?**
`<<<<<<<` открывает блок с содержимым **текущей** ветки (HEAD, «ours» — та, в которую
делают слияние); `=======` — граница между вариантами; `>>>>>>>` закрывает блок с
содержимым **вливаемой** ветки («theirs», с указанием её имени). Всё, что находится вне
этих маркеров, слилось автоматически. Задача разработчика — вручную выбрать или
сконструировать итоговый текст, удалить все три маркера и сделать `git add` файла, что
и означает «конфликт разрешён».

**7. Чем `git revert` отличается от `git reset`? Когда `reset` ломает коллегам работу?**
`revert` создаёт новый коммит, обратный по действию указанному, и не меняет существующую
историю — безопасен для опубликованных веток. `reset` передвигает указатель ветки
(и, с `--hard`, очищает индекс и рабочий каталог), то есть **удаляет** коммиты из ветки.
Если такие коммиты уже были отправлены и коллеги их получили, после `reset --hard` +
`push --force` их локальные ветки разойдутся с сервером: `git pull` даст ошибку
divergence, а принудительный push перезапишет чужие коммиты, сделанные поверх удалённых.
Итог — потеря работы и «битые» ссылки на коммиты в PR и обсуждениях.

## 4. Возникшие затруднения и способы их устранения

1. **Windows без WSL.** Инструменты работали в MSYS2-bash, где пути вида `/c/Users/...`
   понимает сама оболочка, но не native-программы: `git -C /c/...` и `python /tmp/x.py`
   падают с «cannot change to / not found». Решение: для native-утилит использовать
   Windows-пути с прямыми слэшами (`C:/Users/Rozhman/...`), а временные файлы держать не
   в `/tmp`, а в каталоге пользователя. Дополнительно: в MSYS-сборке `gh` отсутствует,
   поэтому операции GitHub выполнялись через SSH и веб-интерфейс.
2. **Пустой репозиторий вместо шаблона.** `git clone` выдал
   `warning: You appear to have cloned an empty repository`, а GitHub API на `/commits`
   отвечал `409` — шаблон сквозного проекта в репозиторий не попал. Решение: работа
   продолжена на минимальном собственном скелете (`README.md`, `src/app.py`,
   `AUTHOR.md`), что не мешает отработать все приёмы Git.
3. **Авторизация push.** Первоначально не было ни SSH-ключей, ни `gh`, ни credential
   helper с сохранёнными данными, поэтому `git push` по HTTPS был невозможен.
   Решение: сгенерирован ключ `ed25519` (`ssh-keygen -t ed25519 -C "..."`), публичная
   часть добавлена в GitHub (Settings → SSH and GPG keys), remote переключён на SSH
   (`git remote set-url origin git@github.com:...`); проверка —
   `ssh -T git@github.com` → `Hi Ro4hman!`.
4. **Конфликт при слиянии `exp/beta` в `exp/alpha`.** Обе ветки меняли одну и ту же первую
   строку `README.md`, поэтому `ort`-стратегия не смогла выбрать вариант. Решение:
   конфликт разобран вручную — прочитан блок между маркерами, выбрана объединённая
   формулировка заголовка, маркеры удалены, файл добавлен через `git add` и зафиксирован
   merge-коммитом. Отработавшие ветки удалены и локально, и в origin, чтобы не оставлять
   мусор.
5. **Автоматическая правка через `sed` в MSYS.** Команда `sed -i '1a\\'` не вставила
   пустую строку (особенность обработки `\` в MSYS-sed), а удаление строк с маркерами
   конфликта оставило дублирующийся заголовок. Обнаружено через
   `head -3 README.md`. Решение: правка выполнена скриптом на Python с явным
   `newline="\n"`, результат проверен и зафиксирован отдельным коммитом
   `docs: пустая строка после заголовка README`.
6. **`.gitignore` не подействовал на `model.pkl`.** Ожидалось, что после добавления
   `*.pkl` файл исчезнет из `git status`, но он остался отслеживаемым:
   `git check-ignore` его не подтверждал, а `git status` показывал `M model.pkl`.
   Причина: `.gitignore` влияет только на **неотслеживаемые** файлы, а `model.pkl` уже был
   в индексе. Решение: `git rm --cached model.pkl` + отдельный коммит; файл остался на
   диске, но вышел из-под контроля версий.
7. **Откат неудачного коммита.** Удаление `src/app.py` уже было отправлено в origin, и
   `git reset --hard` переписал бы общую историю. Решение: `git revert HEAD --no-edit`,
   затем повторная проверка работоспособности — `python src/app.py` и
   `curl -s http://127.0.0.1:8000/health` → `{"status": "ok"}`. Дополнительно проверено,
   что revert-коммит вернул только один файл (`1 file changed, 41 insertions(+)`),
   а остальная история осталась на месте.
8. **Расхождение веток после эксперимента.** После слияния `exp/*` в `main` ветка
   `feature/readme` оказалась позади, и PR мог стать конфликтным. Решение:
   `git merge origin/main` внутри `feature/readme` до открытия PR, конфликт заголовка
   разрешён в пользу документированной версии ветки.

## 5. Ссылки

- Репозиторий проекта: <https://github.com/Ro4hman/nids-service-BrilevRoman>
- PR с документацией (`feature/readme` → `main`):
  <https://github.com/Ro4hman/nids-service-BrilevRoman/compare/main...feature/readme>
- PR с отчётом (`docs/lab01-report` → `main`):
  <https://github.com/Ro4hman/nids-service-BrilevRoman/pull/1>
