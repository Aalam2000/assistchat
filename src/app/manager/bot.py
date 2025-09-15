# src/app/manager/bot.py
from src.app.workers.telegram import TelegramWorker

class BotManager:
    def __init__(self):
        self.workers = {}  # {resource_id: worker}

    async def start(self, user_id: str):
        # TODO: получить ресурсы из БД и запустить их
        return {"ok": True, "started": []}

    async def stop(self, user_id: str):
        # TODO: остановить все ресурсы пользователя
        return {"ok": True, "stopped": []}

    def preflight(self, user_id: str):
        # TODO: проверить ресурсы пользователя
        return {"ok": True, "results": {}}

bot_manager = BotManager()
