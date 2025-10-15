[//]: # (src/app/resources/telegram/logic.md)
# 🤖 Telegram — логика работы ресурса AssistChat

---

## 🧩 1. Логика работы ресурса

**Роль:**  
Telegram-провайдер — автономный агент, подключённый к конкретному Telegram-аккаунту пользователя (через `string_session`).  
Работает только если:
- `user.bot_enabled = True`
- `resource.status = 'active'`

### Этапы работы:
1. **Подключение**
   - Пользователь вводит `App ID`, `App Hash`, `String Session` (или проходит префлайт).
   - После этого создаётся активная сессия Telethon-клиента, привязанная к пользователю.

2. **Инициализация правил и промптов**
   - Загружаются поля:
     - `prompts.settings`, `prompts.rules_common`, `prompts.rules_dialog`
     - `lists.whitelist`, `lists.blacklist`
     - `extra.allow_groups`
   - Эти данные управляют поведением ассистента.

3. **Работа в группах**
   - Если `extra.allow_groups=True`, worker слушает входящие сообщения в группах, где присутствует аккаунт.
   - Проверяет отправителя:
     - если в `blacklist` → игнорируется;
     - если в `whitelist` → разрешено взаимодействие.

4. **Диалоги с пользователями**
   - При личных сообщениях применяется логика промптов и формируется ответ через OpenAI API.
   - История диалога с каждым собеседником сохраняется в таблице `messages`.
   - Для оптимизации контекста в процессе общения используется не вся история, а только последние **X сообщений**, где X задаётся в настройках ресурса (`limits.history_length`).
     - Старые сообщения не удаляются, но не участвуют в контексте диалога; они доступны в архиве для анализа.

5. **Системная логика**
   - Все сообщения логируются в таблицу `messages`.
   - Контроль расхода токенов и лимитов (см. ниже).
   - Если `bot_enabled=False` или `status='pause'` — соединение закрывается.

---

## ⚙️ 2. Таблица `resources` — хранение и структура данных

**Назначение:**  
Таблица `resources` хранит все подключённые интеграции пользователя (Telegram, Zoom, Voice и т.п.).  
Каждая строка — отдельный ресурс (учётка, канал, интеграция), принадлежащий пользователю.

| Поле | Тип | Назначение |
|------|-----|-------------|
| `id` | int | Уникальный идентификатор ресурса |
| `user_id` | int | Владелец (внешний ключ на `users.id`) |
| `provider` | str | Тип ресурса (`telegram`, `zoom`, `voice` и т.д.) |
| `name` | str | Отображаемое имя в интерфейсе |
| `status` | enum | `active` / `pause` / `error` / `ready` |
| `meta_json` | JSON | Полный набор параметров, как в `providers.py` |
| `created_at` | datetime | Время создания |
| `updated_at` | datetime | Последнее обновление |
| `last_activity` | datetime | Последний контакт/ответ от провайдера |
| `usage_today` | int | Сумма токенов за текущий день |
| `cost_today` | float | Стоимость за текущий день |
| `error_message` | str | Текст последней ошибки (если статус `error`) |

**Содержимое `meta_json` для Telegram:**

```json
{
  "creds": {
    "app_id": 123456,
    "app_hash": "xxxx",
    "string_session": "1ABCD...",
    "code": ""
  },
  "extra": {
    "phone_e164": "+99450XXXXXXX",
    "allow_groups": true,
    "billing_mode": "per_token",
    "provider": "telethon"
  },
  "lists": {
    "whitelist": ["mehman", "ahmad"],
    "blacklist": ["bot123"]
  },
  "prompts": {
    "settings": "...",
    "rules_common": "...",
    "rules_dialog": "..."
  },
  "limits": {
    "tokens_limit": 50000,
    "autostop": true
  }
}
```

## 🖥️ 3. Отображение на странице /resources

На странице “Ресурсы” каждая строка таблицы отображает ключевую информацию о ресурсе:

Колонка	Источник данных	Пример
Провайдер	resource.provider	Telegram
Название	resource.name	Telegram #1
Статус	resource.status	🟢 active / ⏸ pause / 🔴 error
Активность	last_activity	2025-10-11 20:45
Сегодня (токены)	usage_today	324
Стоимость (AZN)	cost_today	0.08
Управление	кнопки “Открыть”, “Пауза”, “Удалить”	—
Кнопка “Открыть”

Ведёт на /resources/telegram/{resource.id}

Загружает HTML-страницу resources/telegram.html, где строится форма на основе схемы из providers.py

Все данные подставляются из resource.meta_json

Кнопка “Пауза/Активировать”

Меняет status ресурса и обновляет интерфейс без перезагрузки (AJAX через /api/resource/status)

Кнопка “Удалить”

Помечает status='deleted' и убирает из активных (без удаления из БД)

## 💾 4. Как сохраняются данные сессии

*При нажатии “Сохранить” в форме Telegram:*

- фронт отправляет JSON на /api/resource/update/{id}

- данные валидируются функцией validate_provider_meta("telegram", meta_json)

- при успехе обновляется meta_json, updated_at и status='ready'.

- При успешном подключении Telethon:

- status меняется на active

- last_activity обновляется

- string_session сохраняется в meta_json.creds.string_session

*При разрыве соединения или ошибке:*

- status → error

- error_message фиксируется для отображения в таблице

- worker автоматически перезапускается, если bot_enabled=True.

## 💰 5. Контроль токенов и биллинг

*Процесс:*

- Каждый ответ Telegram-агента проходит через OpenAI API, фиксируется usage.total_tokens.

- В таблице messages:

- tokens_used

- cost_azn

- model

- timestamp

*В usage_summary (по user_id, provider, date):*

- tokens_total

- cost_total

- limit_exceeded

*Менеджер (bot/manager.py) раз в сутки:*

- суммирует расход токенов;

- при превышении лимита — ставит status='pause' и уведомляет пользователя;

- если autostop=True — worker останавливается немедленно.

*Финансовая модель:*

- 1 токен = X AZN (указывается в config.py)

- per_token: стоимость = токены × ставка

- per_message: фикс за сообщение

- flat_rate: фикс в день, токены — только для статистики