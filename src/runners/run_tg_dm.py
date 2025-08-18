import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
import yaml
from aiogram.types import Message

from integrations.telegram.client import TelegramClient
from integrations.openai.client import OpenAIChat
from runtime.messaging import memory, rate_limit
from runtime.language.detector import detect

# ---------- helpers ----------
def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def truncate(s: str, limit: int) -> str:
    s = s or ""
    return s if len(s) <= limit else s[: max(0, limit - 3)] + "..."

# ---------- main ----------
async def main():
    # env
    load_dotenv()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not tg_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    # configs
    root = Path(__file__).resolve().parents[1]
    tg_cfg = load_yaml(root / "integrations" / "telegram" / "settings.yaml")
    oa_cfg = load_yaml(root / "integrations" / "openai" / "settings.yaml")
    msg_cfg = load_yaml(root / "runtime" / "messaging" / "settings.yaml")
    lang_cfg = load_yaml(root / "runtime" / "language" / "settings.yaml")
    log_cfg = load_yaml(root / "observability" / "logging" / "settings.yaml")

    # logging
    lvl = getattr(logging, (log_cfg.get("level") or "INFO").upper(), logging.INFO)
    logging.basicConfig(level=lvl, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("tg_mvp")

    # clients
    tg = TelegramClient(tg_token, tg_cfg)
    oa = OpenAIChat(oa_cfg)

    cooldown = int(tg_cfg.get("limits", {}).get("per_chat_cooldown_sec", 2))
    max_in = int(tg_cfg.get("limits", {}).get("max_input_chars", 2000))
    max_out = int(tg_cfg.get("limits", {}).get("max_output_chars", 800))
    memory_turns = int(msg_cfg.get("memory_turns", 8))
    supported = lang_cfg.get("supported", ["ru", "az", "en"])
    fallback = lang_cfg.get("fallback", "ru")

    system_prompt = oa_cfg.get("system_prompt", "Отвечай кратко и по делу.")

    async def on_text_dm(message: Message):
        chat_id = message.chat.id
        msg_id = message.message_id
        text_in = (message.text or "").strip()
        if not text_in:
            return

        text_in = truncate(text_in, max_in)

        # язык
        lang = detect(text_in, supported=supported, fallback=fallback)

        # контекст
        history = memory.get_context(chat_id)

        # вызов OpenAI в фоне, чтобы не блокировать ивент-луп
        def _ask():
            return oa.generate_reply(system_prompt=system_prompt, history=history, user_text=text_in)

        try:
            # перед ответом проверим кулдаун
            if not rate_limit.allow(chat_id, cooldown):
                left = rate_limit.next_allowed_in(chat_id, cooldown)
                # мягко промолчим; если хочешь — можно отправлять уведомление:
                # await tg.send_text(chat_id, f"Подождите {left:.1f}с")
                return

            reply = await asyncio.to_thread(_ask)
            text_out = truncate(reply.text, max_out)

            # отправка
            await tg.send_text(chat_id, text_out)

            # память
            memory.append(chat_id, "user", text_in, max_turns=memory_turns)
            memory.append(chat_id, "assistant", text_out, max_turns=memory_turns)

            log.info(
                "dm handled",
                extra={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "duration_ms": reply.latency_ms,
                    "input_len": len(text_in),
                    "output_len": len(text_out),
                },
            )
        except Exception as e:
            log.exception(f"handler error chat={chat_id} msg={msg_id}: {e}")
            # мягкая заглушка
            try:
                await tg.send_text(chat_id, "Сбой при обработке запроса. Попробуйте ещё раз.")
            except Exception:
                pass

    # маршрутизация
    tg.dp.include_router(tg.build_dm_router(on_text_dm))

    # старт
    print("✅ Telegram DM MVP is running (polling). Press Ctrl+C to stop.")
    await tg.start_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Stopped.")
