"""
src/app/resources/telegram/__init__.py
──────────────────────────────────────
Инициализация Telegram-ресурса платформы AssistChat.

Назначение:
    • Подключает API-роуты Telegram (активация, управление, проверка статуса);
    • Обеспечивает импорт воркера TelegramWorker при старте менеджера;
    • Позволяет централизованно обращаться к Telegram-ресурсу как модулю.
"""

from .router import router
from .telegram import TelegramWorker

__all__ = ["router", "TelegramWorker"]
