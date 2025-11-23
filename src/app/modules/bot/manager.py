"""
src/app/modules/bot/manager.py
──────────────────────────────────────────────
Централизованное управление ботами AssistChat.

Назначение:
    • Запускает и останавливает все активные ресурсы пользователя;
    • Проверяет флаг user.bot_enabled перед активацией;
    • Работает с провайдерами динамически через src/app/providers.py;
    • Поддерживает реестр активных воркеров (по user_id и resource_id);
    • Позволяет безопасно перезапускать ресурсы без рестарта сервера.
"""

import asyncio
from typing import Dict, Any
from src.app.core.db import SessionLocal
from src.models.user import User
from src.app import providers


class BotManager:
    """Менеджер, управляющий воркерами всех пользователей."""

    def __init__(self):
        # self.workers[user_id][resource_id] = worker_instance
        self.workers: Dict[int, Dict[str, Any]] = {}

    def preflight(self, user_id: int) -> dict:
        """Проверка, активен ли бот у данного пользователя."""
        active = user_id in self.workers and bool(self.workers[user_id])
        resources = list(self.workers.get(user_id, {}).keys())
        return {"ok": True, "active": active, "resources": resources}

    async def start(self, user_id: int) -> dict:
        print(f"[BOT_MANAGER] ▶ start() called for user_id={user_id}")
        db = SessionLocal()
        user = db.get(User, user_id)
        if not user:
            db.close()
            return {"ok": False, "error": "USER_NOT_FOUND"}
        if not user.bot_enabled:
            db.close()
            return {"ok": False, "error": "BOT_DISABLED"}

        # Получаем все активные ресурсы (через providers)
        active_resources = providers.get_active_resources(db)
        if not active_resources:
            db.close()
            return {"ok": True, "message": "no_active_resources"}

        # создаём словарь воркеров для пользователя
        self.workers[user.id] = self.workers.get(user.id, {})

        total_started = 0
        for provider_name, resources_list in active_resources.items():
            worker_cls = providers.import_worker(provider_name)
            if not worker_cls:
                print(f"[BOT_MANAGER] ❌ Пропущен {provider_name}: нет воркера")
                continue

            for r in resources_list:
                if r.user_id != user.id:
                    continue  # запуск только своих ресурсов
                if str(r.id) in self.workers[user.id]:
                    print(f"[BOT_MANAGER] ⏩ {r.id} уже активен → skip")
                    continue

                try:
                    print(f"[BOT_MANAGER] 🚀 Запуск {provider_name} для resource={r.id}")
                    worker = worker_cls(r)
                    asyncio.create_task(worker.start())
                    self.workers[user.id][str(r.id)] = worker
                    total_started += 1
                except Exception as e:
                    print(f"[BOT_MANAGER] ❗ Ошибка при запуске {provider_name}/{r.id}: {e}")

        db.close()
        return {"ok": True, "message": f"{total_started} worker(s) started"}

    async def stop(self, user_id: int) -> dict:
        """Останавливает все активные ресурсы пользователя."""
        user_workers = self.workers.pop(user_id, {})
        if not user_workers:
            return {"ok": True, "message": "not_running"}

        for rid, worker in list(user_workers.items()):
            try:
                await worker.stop()
                print(f"[BOT_MANAGER] 🟥 stopped worker {rid}")
            except Exception as e:
                print(f"[BOT_MANAGER] ⚠️ error stopping {rid}: {e}")

        return {"ok": True, "message": "bot_stopped"}


# ───────────────────────────────────────────────────────────────────────────────
# Глобальные функции для API
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
