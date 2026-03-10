# AssistChat

AssistChat — платформа на FastAPI для запуска AI-интеграций (“ресурсов”) через веб-интерфейс + фонового воркера.
Одна кодовая база обслуживает:
- Web UI (Jinja2 templates + static)
- API (FastAPI)
- Bot/worker (фоновые процессы ресурсов)
- Миграции БД (Alembic)

## Стек (факт по репозиторию)
- FastAPI + Starlette, Jinja2
- SQLAlchemy 2.x + Alembic
- Postgres 16.x (в docker-compose)
- Telethon (Telegram)
- OpenAI SDK (есть в requirements)
- auto-i18n-lib (переводы UI)
:contentReference[oaicite:1]{index=1}

---

## Runtime / контейнеры

### DEV (`docker-compose.dev.yml`)
Сервисы:
- `db` (postgres)
- `migrate` (alembic upgrade head)
- `web` (uvicorn src.app.main:app + autoreload)
- `botworker` (worker_entry под watchfiles)

`web` и `botworker` запускаются из одного image (`assistchat-api-local`), код маунтится в `/app`.
:contentReference[oaicite:2]{index=2}

### PROD (`docker-compose.prod.yml`)
Сервисы:
- `db`
- `migrate` (alembic upgrade head, с DB_HOST=db)
- `web`
- `botworker` (python -m src.app.modules.bot.worker_entry)

:contentReference[oaicite:3]{index=3}

---

## Ключевая архитектура кода

### Entry points
- Web/API: `src/app/main.py`
- Legacy (есть в проекте): `src/app/main_legacy.py`
- Worker: `src/app/modules/bot/worker_entry.py`
- Provider schema: `src/app/providers.py`
:contentReference[oaicite:4]{index=4}

### Core (`src/app/core/`)
База инфраструктуры приложения:
- `config.py`, `db.py`, `middleware.py`, `security.py`, `templates.py`
- диалоговая подсистема: `dialog_service.py`, `dialog_graph.py`, `dialog_store.py`, `dialog_lock.py`
- runtime промпта/транспорта: `prompt_runtime.py`, `ai_transport.py`


### Bot module (`src/app/modules/bot/`)
- `manager.py` — запуск/остановка активных ресурсов
- `router.py` — API для управления ботом
- `worker_entry.py` — точка входа фонового воркера


### Ресурсы (`src/app/resources/`)
Каждый ресурс — отдельный модуль со своим `router.py` и `settings.yaml`:
- `telegram/` (есть `telegram.py` — логика ресурса)
- `zoom/` (есть `transcribe.py`)
- `api_keys/`
- `prompt/`


### Web UI (`src/web/`)
- `templates/` — страницы (auth/profile/resources + страницы конкретных ресурсов)
- `static/js/` — фронтовая логика (api_keys.js, prompt.js, telegram.js, zoom.js и т.д.)
- `static/lang/` — JSON переводы (ru/en)
:contentReference[oaicite:8]{index=8}

---

## База данных (факт по последнему дампу схемы)

Текущие таблицы в DB:
- `users`
- `resources`
- `dialogs`
- `messages`
- `leads`
- `updates_seen`
- `alembic_version`
:contentReference[oaicite:9]{index=9}

Важно: по отчёту **ORM содержит модели**, которых **нет в БД** на текущей ревизии Alembic:
- `prompts`, `service_accounts`, `service_rules`, `tg_accounts` — *в ORM есть, в DB отсутствуют*.
Это означает, что миграции под эти таблицы либо ещё не созданы, либо не применены в этой базе.
:contentReference[oaicite:10]{index=10}

---

## Структура репозитория (коротко)

- `src/app/` — FastAPI приложение, core, modules, resources, routes
- `src/models/` — ORM-модели
- `src/web/` — HTML шаблоны + static (css/js/img/lang)
- `src/alembic/` — миграции
- `branding/` — профили стиля/тона
- `tmp/` — временные файлы/отчёты (должна быть в корне и игнорироваться Git)
:contentReference[oaicite:11]{index=11}

---

## Запуск (команды по факту compose-файлов)

### DEV
```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml logs -f web
docker compose -f docker-compose.dev.yml logs -f botworker