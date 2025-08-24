# 📂 Структура проекта `assistchat`

```text
assistchat/
├── .github/
│   └── workflows/
│       └── deploy.yml              # CI/CD workflow
│
├── branding/                       # Стили ответов, бренд-материалы
│   └── style_profile.md
│
├── docker/
│   └── app/
│       └── Dockerfile              # Docker-образ для приложения
│
├── scripts/                        # Python-утилиты (seed, онбординг, логгер, респондер)
│   ├── create_user.py
│   ├── seed_tg_account.py
│   ├── onboard_tg_session.py
│   ├── tg_user_dm_logger.py
│   └── tg_user_dm_responder.py
│
├── src/
│   ├── alembic/                    # Миграции базы
│   │   ├── versions/
│   │   └── env.py
│   ├── app/                       # Веб-приложение (API, модели)
│   │   ├── static/
│   │   │   └── mess.js
│   │   ├── templates/
│   │   │   └── index.html
│   │   ├── main.py
│   │   └── models.py
│   │
│   ├── common/                     # Общие сервисы (config, DB)
│   │   ├── config.py
│   │   └── db.py
│   │
│   ├── integrations/               # Интеграции (Telegram, OpenAI и др.)
│   │   └── telegram_client.py
│   │
│   ├── models/                     # SQLAlchemy-модели
│   │   ├── tg_account.py
│   │   └── message.py
│   │
│   ├── observability/              # Логирование и метрики
│   │   ├── logging.py
│   │   └── metrics.py
│   │
│   ├── runners/                    # Точки запуска (боты и сервисы)
│   │   ├── run_tg_dm.py
│   │   └── run_web.py
│   │
│   └── runtime/                    # Бизнес-логика: обработка сообщений, язык, память
│       ├── language.py
│       ├── memory.py
│       └── message_handler.py
│
└── tests/                          # Автотесты
    ├── test_api.py
    └── test_tg.py
```

---

## 🔹 Кратко по слоям

- **scripts/** → Python-утилиты (seed, онбординг, логгер, респондер).  
- **src/app/** → веб-приложение (API, модели).  
- **src/common/** → общие сервисы (config, DB).  
- **src/integrations/** → интеграции (Telegram, OpenAI).  
- **src/models/** → SQLAlchemy-модели (`tg_account`, `message`).  
- **src/observability/** → логирование и метрики.  
- **src/runners/** → точки запуска (бот и сервисы).  
- **src/runtime/** → бизнес-логика: обработка сообщений, язык, память.  
- **alembic/** → миграции базы.  
- **branding/** → стилистика ответов.  
- **docker/** → Dockerfile.  


---

# assistchat - ПОДСКАЗКИ

**1️⃣ Пересборка с нуля и запуск**

```bash
     cd /var/www/assistchat
     docker compose down --remove-orphans
     docker compose up -d --build
```
**Если запустил в фоне**
```bash
     docker compose up -d
```
** Смотреть все сервисы сразу
```bash
     docker compose logs -f
```
** Смотреть конкретный контейнер
```bash
     docker compose logs -f tg_user
```

* `--remove-orphans` удаляет лишние контейнеры, которых нет в `docker-compose.yml`.
* `--build` пересобирает образы по Dockerfile.

---

**2️⃣ Перезапуск без пересборки**

```bash
     cd /var/www/assistchat
     docker compose restart
```

---

**3️⃣ Остановка контейнеров**

```bash
     cd /var/www/assistchat
     docker compose down
```
* Это остановит и удалит контейнеры, но оставит образы и volume'ы.

---

**4️⃣ Проверка статуса**

```bash
     cd /var/www/assistchat
     docker compose ps
```

**5️⃣ Просмотр логов**

```bash
     docker compose logs -f
     docker compose logs -f api
```
**5️⃣ Посмотреть тома !**
```bash
     docker volume ls
```
---

### 🔎 Проверка базы данных (Postgres)

Для входа в контейнер Postgres и работы с SQL используем psql:

**Войти в контейнер с Postgres**
```bash
    docker exec -it assistchat-db-1 psql -U postgres -d assistchat
```
**Показать все таблицы**
```bash
     \dt
```
**Показать схему конкретной таблицы (структура + типы столбцов)**
```bash
     \d имя_таблицы
```
**Показать все базы данных**
```bash
     \l
```
**Переключиться на другую базу**
```bash
     \c имя_базы
```
**Выполнить SQL-запрос (например, вывести первые 10 строк таблицы tg_account)**
```bash
    SELECT * FROM tg_account LIMIT 10;
```
**Выйти из psql**
```bash
     \q
```
---

alembic_version
messages
updates_seen
tg_accounts
