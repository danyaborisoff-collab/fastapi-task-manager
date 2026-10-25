# Практическая работа № 3. Тестирование, контейнеризация и CI/CD

[![CI](https://github.com/danyaborisoff-collab/fastapi-task-manager/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/danyaborisoff-collab/fastapi-task-manager/actions/workflows/ci.yml)

**Задание 7.** Исходный проект — REST API «Менеджер задач» из практической работы № 2. [Отчёт по предыдущей работе](docs/lab6-report.md).

## Цель и результат

API дополнено автоматическими тестами на реальном PostgreSQL, линтером Ruff, многоэтапной сборкой Docker и конвейером GitHub Actions. Проверены отрицательный сценарий CI с намеренно сломанным тестом и последующее исправление в одном pull request.

## Тестирование

Тесты находятся в `tests/test_api.py`, фикстуры — в `tests/conftest.py`. Всего **25 тестовых случаев** с учётом параметризации.

| № | Обязательная проверка | Тест |
|---|---|---|
| 1 | Создание пользователя — 201 | `test_user_roundtrip` |
| 2 | Повторный email — 409 | `test_duplicate_email` |
| 3 | Невалидный email — 422 | `test_invalid_user` |
| 4 | Создание задачи — 201 | `test_task_roundtrip` |
| 5 | Несуществующий владелец — 404 | `test_missing_owner` |
| 6 | Фильтр done и пагинация | `test_filters_and_pagination` |
| 7 | PATCH меняет только переданные поля | `test_patch_partial_and_clear_description` |
| 8 | DELETE, затем GET — 404 | `test_delete` |
| 9 | Заголовок X-Process-Time | `test_process_time_header` |

Дополнительно проверяются длина названия, параметры пагинации, явные null, пустой PATCH, смена владельца, отсутствие записей, несуществующая задача и документация OpenAPI.

### Изоляция базы и dependency_overrides

Фикстура `test_engine` создаёт отдельный асинхронный движок по `TEST_DATABASE_URL`. Разрешены только базы с суффиксом `_test`; очистка требует `ALLOW_TEST_DB_RESET=1`. Перед каждым тестом таблицы очищаются командой `TRUNCATE … RESTART IDENTITY CASCADE`.

Подмена выполняется через `app.dependency_overrides[get_session] = override_get_session`: обработчики получают сессии тестовой БД. После теста подмена снимается в `finally`. Продукционная сессия не используется для запросов тестового клиента. Схему тестовой БД создаёт Alembic, а не `create_all`.

В `pytest.ini` установлен session scope для event loop фикстур и тестов. HTTP-запросы выполняются через `HTTPX AsyncClient` и `ASGITransport` без внешнего HTTP-сервера; SQL-запросы идут в настоящий PostgreSQL, без SQLite и моков БД.

### Локальный запуск тестов — PowerShell

Требования: Python 3.11+, запущенный Docker Desktop. Команды из корня проекта. База `tasks_test` создаётся один раз; если уже существует, повторять `createdb` не нужно.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
docker compose up -d db
docker compose exec db createdb -U app tasks_test
$env:DATABASE_URL = 'postgresql+asyncpg://app:app@127.0.0.1:5433/tasks_test'
$env:TEST_DATABASE_URL = $env:DATABASE_URL
$env:ALLOW_TEST_DB_RESET = '1'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:DATABASE_URL
Remove-Item Env:TEST_DATABASE_URL
Remove-Item Env:ALLOW_TEST_DB_RESET
```

После `up -d db` необходимо дождаться готовности PostgreSQL (`docker compose ps`: healthy). Переменные окружения имеют приоритет над `.env`; после тестов они удаляются, чтобы не запустить основное приложение с тестовой БД. Тесты удаляют записи в выбранной тестовой БД.

### Запуск тестов через Docker Compose

```powershell
docker compose --profile test run --build --rm tests
```

Команда поднимает отдельный `test-db` с базой `tasks_test`, ждёт healthcheck, применяет миграции и выполняет тесты в контейнере. Тестовая БД хранится в tmpfs, не использует том `pgdata` основной БД и не публикует порт хоста.

## Контейнеризация

### Dockerfile

Многоэтапная сборка состоит из:

- `builder` — установка Python-зависимостей в `/opt/venv`;
- `runtime-base` — код API, миграции и готовое окружение;
- `test` — отдельный образ с pytest, Ruff и тестами;
- `runtime` — финальная стадия приложения, без тестовых зависимостей.

Образ приложения основан на `python:3.12-slim-bookworm`. Процесс запускается от пользователя **10001:10001**, не root. Секреты, `.env`, Git-история и отчётные материалы исключены из build context через `.dockerignore`.

### Сервисы Compose

| Сервис | Назначение | Условие запуска |
|---|---|---|
| `db` | PostgreSQL 16, база `tasks`, постоянный том `pgdata` | Healthcheck `pg_isready` |
| `migrate` | Однократный `alembic upgrade head` | `db: service_healthy` |
| `app` | Uvicorn и FastAPI, порт 8000 | БД готова, миграции завершились успешно |
| `test-db` | Изолированная PostgreSQL для тестов | Профиль `test`, healthcheck |
| `tests` | Миграции тестовой БД и pytest | Тестовая БД готова |

Миграции вынесены в отдельный одноразовый сервис. Если миграция завершится с ошибкой, зависимое приложение не стартует. И `migrate`, и `app` используют финальный runtime-образ и непривилегированного пользователя.

Запуск полного приложения:

```powershell
docker compose up --build -d app
docker compose ps
docker compose logs app migrate
```

Swagger UI: <http://127.0.0.1:8000/docs>. Проверка таблиц:

```powershell
docker compose exec db psql -U app -d tasks -c '\dt'
```

Перед контейнерным запуском нужно остановить локальный Uvicorn, если он уже занимает порт 8000. Остановка без удаления постоянных данных:

```powershell
docker compose --profile test down
```

## GitHub Actions

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

```text
push / pull_request / workflow_dispatch
              ├── lint: Ruff + проверка форматирования
              └── test: PostgreSQL + Alembic + pytest
                         + тесты через Compose
                         + запуск app через Compose и проверка UID
                              ↓ needs: [lint, test]
                    build: только main, не pull_request
                              ↓
                 GHCR + Docker Hub
```

| Job | Действия |
|---|---|
| `lint` | Установка dev-зависимостей, `ruff check .`, `ruff format --check .` |
| `test` | PostgreSQL service container, миграции, 25 тестов, тестовый Compose, запуск полного стека, HTTP-проверка и UID 10001 |
| `build` | Buildx, сборка runtime и публикация образа с тегами `latest` и `sha-<полный SHA>` |

Runner — Ubuntu 24.04, Python в CI — 3.12. Прямые зависимости зафиксированы, pip и BuildKit используют кэш. Actions закреплены по SHA. Тестовый JUnit-отчёт сохраняется как artifact; контейнеры CI очищаются даже после ошибки.

На любой push и pull request выполняются lint и test. В ветках и PR публикация пропускается. После успешных lint и test при push в main запускается build. Ручной `workflow_dispatch` из main также позволяет повторить публикацию. Сбой test или lint блокирует build через `needs`.

### Намеренно проваленный pipeline и исправление

[Pull request №1](https://github.com/danyaborisoff-collab/fastapi-task-manager/pull/1).

В `test_user_roundtrip` корректное ожидание `response.json() == created` временно заменено на сравнение с `{"intentionally": "broken"}`. Код приложения не менялся ради получения ошибки. В результате тест падает с AssertionError. Затем корректное ожидание восстановлено в той же ветке.

| Этап | Запуск | Результат |
|---|---|---|
| Намеренно неверное ожидание | [Красный CI](https://github.com/danyaborisoff-collab/fastapi-task-manager/actions/runs/40243875440) | lint — success, test — failure (exit 1), build — skipped |
| Исправление теста в PR | [Зелёный CI](https://github.com/danyaborisoff-collab/fastapi-task-manager/actions/runs/40244020419) | lint и test — success, build — skipped (PR) |
| Merge в main и публикация | [CI main](https://github.com/danyaborisoff-collab/fastapi-task-manager/actions/runs/40244713548) | lint, test, build — success; образ опубликован в обоих реестрах |

Скриншот проваленного запуска:

![Красный pipeline](docs/screenshots/lab7-ci-failed.svg)

Скриншот успешного запуска:

![Зелёный pipeline](docs/screenshots/lab7-ci-success.svg)

Скриншоты получены с реальных страниц GitHub Actions. [Локальный вывод намеренно проваленного теста](docs/evidence/lab7-intentional-failure.txt) сохранён отдельно от результатов CI.

### Найденные ошибки конфигурации

| Ошибка | Причина | Исправление |
|---|---|---|
| `alembic check` предлагал удалить существующие таблицы | Линтер удалил импорт, выполнявший регистрацию моделей, и metadata оказалась пустой | Metadata берётся через явную ссылку `models.User.metadata` |
| `ModuleNotFoundError: No module named 'app'` при запуске консольного pytest | Рабочая папка не попадала в путь импорта так же, как при `python -m pytest` | В `pytest.ini` добавлен `pythonpath = .`, CI запускает `python -m pytest` |

## Опубликованные образы

### GitHub Container Registry

Образ опубликован и доступен анонимно. Для фиксированного тега `sha-b593ed8f072fd66c419e60129eb7bf13935686ac` запрос manifest вернул HTTP 200. Digest: `sha256:03cc391605ae0c2e43bc6050e88616e3f70e3b7cb6d020eed6020e32bc2e5397`.

- [Страница пакета GHCR](https://github.com/danyaborisoff-collab/fastapi-task-manager/pkgs/container/fastapi-task-manager)
- Имя: `ghcr.io/danyaborisoff-collab/fastapi-task-manager:latest`
- Тег конкретной сборки: `ghcr.io/danyaborisoff-collab/fastapi-task-manager:sha-b593ed8f072fd66c419e60129eb7bf13935686ac`

### Docker Hub

Образ опубликован. API Docker Hub подтвердил фиксированный тег `sha-b593ed8f072fd66c419e60129eb7bf13935686ac`; digest `sha256:03cc391605ae0c2e43bc6050e88616e3f70e3b7cb6d020eed6020e32bc2e5397` совпадает с GHCR.

- [Страница образа Docker Hub](https://hub.docker.com/r/ttdany/fastapi-task-manager)
- Имя: `ttdany/fastapi-task-manager:latest`
- Тег конкретной сборки: `ttdany/fastapi-task-manager:sha-b593ed8f072fd66c419e60129eb7bf13935686ac`

Docker Hub требует репозиторных секретов `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN`. Проверка наличия обоих секретов обязательна: при пустом секрете build завершается с ошибкой. В первом запуске публикация Docker Hub была пропущена из-за недоступных секретов; после их настройки повторный запуск успешно опубликовал оба образа. GHCR использует встроенный `GITHUB_TOKEN` с `packages: write` только в build.

### Подтверждение публикации

[Данные проверки реестров](docs/evidence/lab7-registries.json). Оба тега `sha-b593ed8f072fd66c419e60129eb7bf13935686ac` указывают на один и тот же OCI image index. `latest` — подвижный тег и обновляется при следующих успешных сборках; для воспроизводимости используется зафиксированный SHA-тег. Метка `org.opencontainers.image.revision` связывает образ с коммитом исходного кода.

## Контрольные вопросы

### 1. Чем CI отличается от CD (continuous delivery и continuous deployment)?

CI — частая интеграция изменений с автоматическими проверками: линтером, тестами и сборкой. Continuous delivery поддерживает проверенный артефакт готовым к выпуску, но развёртывание может требовать ручного решения. Continuous deployment автоматически развёртывает прошедшие проверки изменения. Этот workflow реализует CI и автоматическую публикацию образа; публикация в реестр не равна развёртыванию сервиса в production.

### 2. Как работает dependency_overrides и зачем он нужен в тестах?

`app.dependency_overrides` — словарь, где ключом служит исходная функция зависимости, значением — её тестовая замена. FastAPI вызывает замену вместо исходной зависимости в Depends. Здесь get_session подменяется фабрикой сессий отдельной PostgreSQL: тесты не затрагивают основную БД и проверяют настоящий SQL. После теста override удаляется, иначе он повлияет на следующие запросы.

### 3. Зачем нужна многоэтапная сборка образа?

Она отделяет установку зависимостей и инструменты сборки от финальной среды запуска. В runtime копируются только нужные результаты; тестовые пакеты остаются в отдельном target. Это сокращает лишнее содержимое и поверхность атаки финального образа и позволяет независимо использовать production- и test-стадии.

### 4. Почему контейнер не следует запускать от root?

При компрометации приложения root даёт процессу больше возможностей внутри контейнера и повышает риски при ошибках настроек, опасных mount-ах или уязвимостях изоляции. Непривилегированный пользователь ограничивает последствия и случайную запись в системные пути. Это дополнительная защита, а не замена остальным мерам безопасности. В проекте приложение и миграции работают от UID/GID 10001.

### 5. Как в GitHub Actions передаются секреты и почему их нельзя хранить в репозитории?

Секреты сохраняются в настройках Actions и передаются шагам через `secrets.NAME`, inputs или переменные окружения. Встроенный GITHUB_TOKEN создаётся для job, его права ограничиваются через permissions. Git-история, форки и копии репозитория делают записанный в коде токен трудноудаляемым; его компрометация открывает доступ к реестру. Маскирование в логах — дополнительная мера, а не разрешение печатать секреты. Публикация выполняется только из main; PR не получает шагов авторизации в реестрах.

### 6. Что произойдёт с job build, если упадёт test? Где это задаётся?

Build будет пропущен, образ не опубликуется. Зависимость задаётся `needs: [lint, test]`; без переопределения поведения через `always()` зависимый job требует успешного завершения предшественников. Дополнительно job-level if ограничивает публикацию основной веткой и исключает pull_request.

### 7. Где лучше применять миграции: при старте контейнера или отдельным шагом в CD?

При старте контейнера проще обеспечить запуск с актуальной схемой в небольшом учебном проекте, но несколько реплик могут одновременно попытаться менять БД, а длительная миграция задерживает старт. Отдельный CD-шаг даёт единый контролируемый запуск, возможность подтверждения и диагностики, однако требует согласовать совместимость старого и нового кода при развёртывании. В Compose используется отдельный одноразовый сервис migrate перед app. В production предпочтителен координированный release/CD-шаг с проверенными миграциями и планом восстановления; downgrade не всегда возвращает удалённые данные.

## Вывод

Реализованы 25 тестовых случаев на реальном PostgreSQL, изоляция тестовой БД через dependency_overrides, многоэтапный Dockerfile и запуск без root. GitHub Actions выполняет Ruff, тесты напрямую и через Docker Compose, проверяет миграции и запуск приложения. В PR продемонстрированы намеренное падение теста и успешное исправление, затем выполнен merge. После успешных проверок образ опубликован в GHCR и Docker Hub; совпадение digest подтверждено через API реестров.
