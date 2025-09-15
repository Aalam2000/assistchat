# src/app/workers/telegram.py
from src.app.workers.base import BaseWorker

class TelegramWorker(BaseWorker):
    async def start(self):
        await super().start()
        # TODO: поднять Telethon клиента
        print(f"[TG] Worker started for resource {self.resource.id}")

    async def stop(self):
        await super().stop()
        # TODO: закрыть Telethon клиента
        print(f"[TG] Worker stopped for resource {self.resource.id}")

    def apply_rules(self, message):
        # TODO: применить whitelist/blacklist/prompt из meta_json
        return True
