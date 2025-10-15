# src/app/modules/bot/worker_entry.py
import asyncio
from src.app.modules.bot.manager import bot_manager
from src.app.core.db import SessionLocal
from src.models.user import User

async def main():
    await asyncio.sleep(5)
    db = SessionLocal()
    users = db.query(User).filter_by(bot_enabled=True).all()
    print(f"[BOT_WORKER] starting {len(users)} users")
    for u in users:
        try:
            await bot_manager.start(u.id)

            # автозапуск активных ресурсов пользователя (в т.ч. Telegram)
            from src.models.resource import Resource
            from src.app.resources.telegram.telegram import TelegramWorker

            resources = db.query(Resource).filter_by(user_id=u.id, status="active").all()
            for res in resources:
                if res.provider == "telegram":
                    try:
                        print(f"[BOT_WORKER] autostart Telegram for user={u.id}, resource={res.label}")
                        worker = TelegramWorker(res)
                        asyncio.create_task(worker.start())
                    except Exception as e:
                        print(f"[BOT_WORKER] Telegram autostart error for {res.label}: {e}")

        except Exception as e:
            print(f"[BOT_WORKER] error for user {u.id}: {e}")

    db.close()
    while True:
        await asyncio.sleep(3600)  # держим процесс живым

if __name__ == "__main__":
    asyncio.run(main())
