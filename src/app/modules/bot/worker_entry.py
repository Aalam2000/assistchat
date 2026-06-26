# src/app/modules/bot/worker_entry.py
import asyncio
import os
import json
import hashlib

from src.app.core.db import SessionLocal
from src.models.resource import Resource
from src.models.user import User
from src.app.resources.telegram.telegram import session_registry
from src.app.resources.telegram_bot.bot import bot_registry
from src.app.resources.prompt.prompt_worker import prompt_registry

POLL_SECONDS = float(os.getenv("BOT_POLL_SECONDS", "2.0"))


def _conf_sig(r: Resource) -> str:
    """
    Сигнатура только по настройкам, которые меняются при сохранении ресурса.
    Важно: НЕ используем updated_at, потому что его трогает telegram worker (_set_state),
    и тогда будет бесконечный рестарт.
    """
    payload = {
        "label": r.label,
        "meta_json": r.meta_json or {},
    }
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


async def main() -> None:
    print(f"[BOT_WORKER] boot. poll={POLL_SECONDS}s", flush=True)

    # Раздельные наборы для каждого типа воркеров
    running_tg:      set[str] = set()
    running_bot:     set[str] = set()
    running_prompt:  set[str] = set()
    sig_tg:          dict[str, str] = {}
    sig_bot:         dict[str, str] = {}
    sig_prompt:      dict[str, str] = {}
    prev_desired_tg:     set[str] | None = None
    prev_desired_bot:    set[str] | None = None
    prev_desired_prompt: set[str] | None = None

    while True:
        desired_tg:     dict[str, Resource] = {}
        desired_bot:    dict[str, Resource] = {}
        desired_prompt: dict[str, Resource] = {}

        db = SessionLocal()
        try:
            rows = (
                db.query(Resource)
                .join(User, User.id == Resource.user_id)
                .filter(Resource.provider.in_(["telegram", "telegram_bot", "prompt"]))
                .filter(User.bot_enabled.is_(True))
                .all()
            )
            for r in rows:
                if r.status != "active":
                    continue
                if r.provider == "telegram":
                    desired_tg[str(r.id)] = r
                elif r.provider == "telegram_bot":
                    desired_bot[str(r.id)] = r
                elif r.provider == "prompt":
                    desired_prompt[str(r.id)] = r
        finally:
            db.close()

        # ── Telegram user-sessions ────────────────────────────────────────
        tg_ids = set(desired_tg.keys())
        if prev_desired_tg is None or tg_ids != prev_desired_tg:
            print(f"[BOT_WORKER] desired telegram active={len(tg_ids)}", flush=True)
            prev_desired_tg = set(tg_ids)

        for rid in sorted(running_tg - tg_ids):
            try:
                await session_registry.stop(rid)
                print(f"[BOT_WORKER] -OFF telegram rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram stop error rid={rid}: {e!r}", flush=True)
            finally:
                running_tg.discard(rid)
                sig_tg.pop(rid, None)

        for rid in sorted(tg_ids - running_tg):
            try:
                await session_registry.ensure_started(desired_tg[rid])
                print(f"[BOT_WORKER] +ON telegram rid={rid}", flush=True)
                running_tg.add(rid)
                sig_tg[rid] = _conf_sig(desired_tg[rid])
            except Exception as e:
                from src.app.modules.bot.guard import BotInactive
                if isinstance(e, BotInactive):
                    print(f"[BOT_WORKER] skip telegram rid={rid}: bot inactive", flush=True)
                else:
                    print(f"[BOT_WORKER] telegram start error rid={rid}: {e!r}", flush=True)
                running_tg.discard(rid)
                sig_tg.pop(rid, None)

        for rid in sorted(tg_ids & running_tg):
            try:
                new_sig = _conf_sig(desired_tg[rid])
                if sig_tg.get(rid) and new_sig != sig_tg[rid]:
                    await session_registry.stop(rid)
                    await session_registry.ensure_started(desired_tg[rid])
                    sig_tg[rid] = new_sig
                    print(f"[BOT_WORKER] ↻RESTART telegram rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram restart error rid={rid}: {e!r}", flush=True)
                running_tg.discard(rid)
                sig_tg.pop(rid, None)

        # ── Telegram bots ─────────────────────────────────────────────────
        bot_ids = set(desired_bot.keys())
        if prev_desired_bot is None or bot_ids != prev_desired_bot:
            print(f"[BOT_WORKER] desired telegram_bot active={len(bot_ids)}", flush=True)
            prev_desired_bot = set(bot_ids)

        for rid in sorted(running_bot - bot_ids):
            try:
                await bot_registry.stop(rid)
                print(f"[BOT_WORKER] -OFF telegram_bot rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram_bot stop error rid={rid}: {e!r}", flush=True)
            finally:
                running_bot.discard(rid)
                sig_bot.pop(rid, None)

        for rid in sorted(bot_ids - running_bot):
            try:
                await bot_registry.ensure_started(desired_bot[rid])
                print(f"[BOT_WORKER] +ON telegram_bot rid={rid}", flush=True)
                running_bot.add(rid)
                sig_bot[rid] = _conf_sig(desired_bot[rid])
            except Exception as e:
                from src.app.modules.bot.guard import BotInactive
                if isinstance(e, BotInactive):
                    print(f"[BOT_WORKER] skip telegram_bot rid={rid}: bot inactive", flush=True)
                else:
                    print(f"[BOT_WORKER] telegram_bot start error rid={rid}: {e!r}", flush=True)
                running_bot.discard(rid)
                sig_bot.pop(rid, None)

        for rid in sorted(bot_ids & running_bot):
            try:
                new_sig = _conf_sig(desired_bot[rid])
                if sig_bot.get(rid) and new_sig != sig_bot[rid]:
                    await bot_registry.stop(rid)
                    await bot_registry.ensure_started(desired_bot[rid])
                    sig_bot[rid] = new_sig
                    print(f"[BOT_WORKER] ↻RESTART telegram_bot rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram_bot restart error rid={rid}: {e!r}", flush=True)
                running_bot.discard(rid)
                sig_bot.pop(rid, None)

        # ── PROMPT воркеры ────────────────────────────────────────────────
        prompt_ids = set(desired_prompt.keys())
        if prev_desired_prompt is None or prompt_ids != prev_desired_prompt:
            print(f"[BOT_WORKER] desired prompt active={len(prompt_ids)}", flush=True)
            prev_desired_prompt = set(prompt_ids)

        for rid in sorted(running_prompt - prompt_ids):
            try:
                await prompt_registry.stop(rid)
                print(f"[BOT_WORKER] -OFF prompt rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] prompt stop error rid={rid}: {e!r}", flush=True)
            finally:
                running_prompt.discard(rid)
                sig_prompt.pop(rid, None)

        for rid in sorted(prompt_ids - running_prompt):
            try:
                await prompt_registry.ensure_started(desired_prompt[rid])
                print(f"[BOT_WORKER] +ON prompt rid={rid}", flush=True)
                running_prompt.add(rid)
                sig_prompt[rid] = _conf_sig(desired_prompt[rid])
            except Exception as e:
                from src.app.modules.bot.guard import BotInactive
                if isinstance(e, BotInactive):
                    print(f"[BOT_WORKER] skip prompt rid={rid}: bot inactive", flush=True)
                else:
                    print(f"[BOT_WORKER] prompt start error rid={rid}: {e!r}", flush=True)
                running_prompt.discard(rid)
                sig_prompt.pop(rid, None)

        for rid in sorted(prompt_ids & running_prompt):
            try:
                new_sig = _conf_sig(desired_prompt[rid])
                if sig_prompt.get(rid) and new_sig != sig_prompt[rid]:
                    await prompt_registry.stop(rid)
                    await prompt_registry.ensure_started(desired_prompt[rid])
                    sig_prompt[rid] = new_sig
                    print(f"[BOT_WORKER] ↻RESTART prompt rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] prompt restart error rid={rid}: {e!r}", flush=True)
                running_prompt.discard(rid)
                sig_prompt.pop(rid, None)

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
