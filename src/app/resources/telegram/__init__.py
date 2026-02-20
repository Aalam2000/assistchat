# src/app/resources/telegram/__init__.py
"""
src/app/resources/telegram/__init__.py
──────────────────────────────────────
Telegram-ресурс (транспорт).

В этой папке:
- router.py    : API для UI (create/save/activate/stop/status/send)
- telegram.py  : Telethon worker + реестр сессий
- settings.yaml: схема формы (meta_json)

Важно:
- Диалог/история/вызов AI — в ЯДРЕ.
- Этот ресурс только получает/отправляет сообщения Telegram и управляет сессией.
"""

from .router import router
from .telegram import TelegramWorker

__all__ = ["router", "TelegramWorker"]
