# src/app/manager/bot.py
from typing import Dict
from src.app.workers.telegram import TelegramWorker
from src.models.resource import Resource
from src.common.db import SessionLocal

class BotManager:
    def __init__(self):
        # {resource_id: worker}
        self.workers: Dict[str, TelegramWorker] = {}

    async def start(self, user_id: int):
        """Запустить все ресурсы пользователя."""
        db = SessionLocal()
        try:
            rows = db.query(Resource).filter(
                Resource.user_id == user_id,
                Resource.provider == "telegram",
                Resource.status == "active",
                Resource.phase == "ready"
            ).all()

            started = []
            for res in rows:
                rid = str(res.id)
                if rid not in self.workers:
                    worker = TelegramWorker(res)
                    await worker.start()
                    self.workers[rid] = worker
                    started.append(rid)
            return {"ok": True, "started": started}
        finally:
            db.close()

    async def stop(self, user_id: int):
        """Остановить все ресурсы пользователя."""
        stopped = []
        for rid, worker in list(self.workers.items()):
            if worker.resource.user_id == user_id:
                await worker.stop()
                self.workers.pop(rid, None)
                stopped.append(rid)
        return {"ok": True, "stopped": stopped}

    def preflight(self, user_id: int):
        """Проверка ресурсов перед запуском (ничего не стартуем)."""
        db = SessionLocal()
        try:
            rows = db.query(Resource).filter(Resource.user_id == user_id).all()
            results = {}
            for res in rows:
                rid = str(res.id)
                ok = (
                        res.provider == "telegram"
                        and bool(((res.meta_json or {}).get("creds") or {}).get("string_session"))
                )
                results[rid] = {
                    "ok": ok,
                    "provider": res.provider,
                    "label": res.label,
                    "reason": None if ok else "NO_SESSION",
                }
            return {"ok": True, "results": results}
        finally:
            db.close()


bot_manager = BotManager()
