import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "src" / "app"

# Структура
dirs = {
    "manager": {
        "bot.py": """\
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
"""
    },
    "workers": {
        "base.py": """\
# src/app/workers/base.py

class BaseWorker:
    def __init__(self, resource):
        self.resource = resource
        self.running = False

    async def start(self):
        self.running = True
        # TODO: инициализация

    async def stop(self):
        self.running = False
        # TODO: остановка процесса

    def check_ready(self) -> bool:
        # TODO: проверить готовность ресурса
        return True
""",
        "telegram.py": """\
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
"""
    }
}


def main():
    for dirname, files in dirs.items():
        dir_path = BASE_DIR / dirname
        dir_path.mkdir(parents=True, exist_ok=True)
        for fname, content in files.items():
            fpath = dir_path / fname
            if not fpath.exists():
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Создан {fpath}")
            else:
                print(f"Пропущен {fpath} (уже существует)")


if __name__ == "__main__":
    main()
