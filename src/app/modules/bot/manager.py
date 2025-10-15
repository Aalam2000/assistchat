"""
src/app/modules/bot/manager.py
──────────────────────────────────────────────
Централизованное управление ботами AssistChat.

Назначение:
    • Запускает и останавливает все активные ресурсы пользователя (Telegram, Voice, Zoom и др.);
    • Проверяет флаг user.bot_enabled перед активацией;
    • Поддерживает реестр активных воркеров (по user_id и resource_id);
    • Позволяет безопасно перезапускать ресурсы без рестарта сервера.
"""

import asyncio
from typing import Dict, Any

from src.app.core.db import SessionLocal
from src.models.user import User
from src.models.resource import Resource

# импорт воркеров ресурсов
from src.app.resources.telegram import TelegramWorker


class BotManager:
    """Менеджер, управляющий воркерами всех пользователей."""

    def __init__(self):
        # self.workers[user_id][resource_id] = worker_instance
        self.workers: Dict[int, Dict[str, Any]] = {}

    def preflight(self, user_id: int) -> dict:
        """Проверка, активен ли бот у данного пользователя."""
        active = user_id in self.workers and bool(self.workers[user_id])
        return {"ok": True, "active": active}

    async def start(self, user_id: int) -> dict:
        print(f"[DEBUG][BOT_MANAGER] start() called for user_id={user_id}")
        db = SessionLocal()
        user = db.get(User, user_id)
        print(f"[DEBUG][BOT_MANAGER] user={user}, bot_enabled={getattr(user, 'bot_enabled', None)}")

        if not user:
            db.close()
            print(f"[DEBUG][BOT_MANAGER] user not found → abort")
            return {"ok": False, "error": "USER_NOT_FOUND"}
        if not user.bot_enabled:
            db.close()
            print(f"[DEBUG][BOT_MANAGER] bot_enabled=False → abort")
            return {"ok": False, "error": "BOT_DISABLED"}

        # получаем активные ресурсы
        resources = db.query(Resource).filter_by(user_id=user.id, status="active").all()
        print(f"[DEBUG][BOT_MANAGER] found {len(resources)} active resources for user {user.id}")

        if not resources:
            db.close()
            print(f"[DEBUG][BOT_MANAGER] no active resources → done")
            return {"ok": True, "message": "no_active_resources"}

        # создаём словарь воркеров для пользователя
        self.workers[user.id] = self.workers.get(user.id, {})
        print(f"[DEBUG][BOT_MANAGER] current worker map keys: {list(self.workers.keys())}")

        for r in resources:
            print(f"[DEBUG][BOT_MANAGER] checking resource {r.id} ({r.provider}, status={r.status})")

            # избегаем дублирования
            if str(r.id) in self.workers[user.id]:
                print(f"[DEBUG][BOT_MANAGER] worker already exists for {r.id} → skip")
                continue

            if r.provider == "telegram":
                print(f"[DEBUG][BOT_MANAGER] creating TelegramWorker for resource {r.id}")
                worker = TelegramWorker(r)
                asyncio.create_task(worker.start())
                self.workers[user.id][str(r.id)] = worker
                print(f"[DEBUG][BOT_MANAGER] TelegramWorker created for {r.id}")

        db.close()
        print(f"[DEBUG][BOT_MANAGER] finished start() for user_id={user_id}")
        return {"ok": True, "message": "bot_started"}

    async def stop(self, user_id: int) -> dict:
        """Останавливает все активные ресурсы пользователя."""
        user_workers = self.workers.pop(user_id, {})
        if not user_workers:
            return {"ok": True, "message": "not_running"}

        for rid, worker in list(user_workers.items()):
            try:
                await worker.stop()
                print(f"[BOT] stopped worker {rid}")
            except Exception as e:
                print(f"[BOT] error stopping {rid}: {e}")

        return {"ok": True, "message": "bot_stopped"}


# ───────────────────────────────────────────────────────────────────────────────
# Глобальные функции для API и Telegram router
# ───────────────────────────────────────────────────────────────────────────────

bot_manager = BotManager()


async def start_user_resources(user: User):
    """Запуск ресурсов конкретного пользователя (если bot_enabled=True)."""
    if not getattr(user, "bot_enabled", False):
        return {"ok": False, "error": "BOT_DISABLED"}
    return await bot_manager.start(user.id)


async def stop_user_resources(user: User):
    """Остановка всех активных ресурсов пользователя."""
    return await bot_manager.stop(user.id)
