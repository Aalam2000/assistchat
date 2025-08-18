# scripts/make_tg_mvp_scaffold.py
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # корень репо (где лежит src/)
SRC = ROOT / "src"

# что создаём: {relative_path: file_content}
FILES = {
    # --- packages ---
    "src/integrations/__init__.py": "",
    "src/integrations/telegram/__init__.py": "",
    "src/integrations/openai/__init__.py": "",
    "src/runtime/__init__.py": "",
    "src/runtime/messaging/__init__.py": "",
    "src/runtime/language/__init__.py": "",
    "src/observability/__init__.py": "",
    "src/observability/logging/__init__.py": "",
    "src/runners/__init__.py": "",

    # --- settings (yaml) ---
    "src/integrations/telegram/settings.yaml": """# Telegram settings for MVP
mode: polling              # polling | webhook
reply_scope: dm_only       # dm_only | mentions_only | all
limits:
  max_input_chars: 2000
  max_output_chars: 800
  per_chat_cooldown_sec: 2
timeouts:
  receive_sec: 30
  send_sec: 30
features:
  allow_groups: false
  allow_voice: false
""",
    "src/integrations/openai/settings.yaml": """# OpenAI settings for MVP
model: gpt-4o-mini
temperature: 0.5
max_tokens_reply: 500
system_prompt: |
  Отвечай кратко и по делу. Поддерживай RU/AZ/EN. Не пиши лишнего.
timeouts:
  request_sec: 20
retries:
  attempts: 2
  backoff_sec: 2
""",
    "src/runtime/messaging/settings.yaml": """# Messaging pipeline settings
memory_turns: 8
truncate:
  input_chars: 2000
  output_chars: 800
""",
    "src/runtime/language/settings.yaml": """# Language detection settings
auto_detect: true
supported: [ru, az, en]
fallback: ru
""",
    "src/observability/logging/settings.yaml": """# Logging settings
level: INFO               # DEBUG | INFO | WARNING | ERROR
format: json              # json | text
fields: [chat_id, message_id, duration_ms]
""",

    # --- stubs (python) ---
    "src/integrations/telegram/client.py": '''"""
Telegram client stub (MVP).
Задача: принимать входящие DM и отправлять ответы.
Заполним реализацию на следующем шаге.
"""
''',
    "src/integrations/openai/client.py": '''"""
OpenAI client stub (MVP).
Задача: получать ответ модели по (system + history + user_message).
Реализацию добавим на следующем шаге.
"""
''',
    "src/runtime/messaging/memory.py": '''"""
In-process memory stub.
Хранит последние N реплик per chat_id. Реализацию добавим далее.
"""
''',
    "src/runtime/messaging/rate_limit.py": '''"""
Simple per-chat cooldown stub.
Предотвращает флуд. Реализацию добавим далее.
"""
''',
    "src/runtime/language/detector.py": '''"""
Language detector stub.
Определяет RU/AZ/EN эвристикой. Реализацию добавим далее.
"""
''',
    "src/runners/run_tg_dm.py": '''"""
Entry point (MVP, DM only).
Будет запускать long-polling Telegram-бота и связывать с OpenAI.
Реализацию добавим на следующем шаге.
"""
''',
}

def ensure_dirs_and_files():
    created, skipped = 0, 0
    for rel, content in FILES.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            skipped += 1
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            created += 1
    return created, skipped

if __name__ == "__main__":
    created, skipped = ensure_dirs_and_files()
    print(f"Scaffold done. Created: {created}, skipped (already existed): {skipped}")
    print(f"Root: {ROOT}")
