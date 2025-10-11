from typing import Callable, Awaitable, Dict, Any
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatType
from aiogram.types import Message

class TelegramClient:
    """Тонкая обёртка вокруг aiogram для DM."""
    def __init__(self, token: str, settings: Dict[str, Any]):
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.settings = settings

    def build_dm_router(self, handler: Callable[[Message], Awaitable[None]]) -> Router:
        router = Router(name="dm_router")

        @router.message(F.chat.type == ChatType.PRIVATE, F.text)
        async def _on_dm(message: Message):
            await handler(message)

        return router

    async def start_polling(self) -> None:
        await self.dp.start_polling(self.bot)

    async def send_text(self, chat_id: int, text: str) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text)
