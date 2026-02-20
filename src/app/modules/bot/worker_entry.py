# src/app/modules/bot/worker_entry.py
import asyncio
import os
import json
import hashlib

from src.app.core.db import SessionLocal
from src.models.resource import Resource
from src.models.user import User
from src.app.resources.telegram.telegram import session_registry

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

    running: set[str] = set()
    prev_desired_ids: set[str] | None = None

    # последняя применённая конфигурация для запущенных ресурсов
    running_sig: dict[str, str] = {}

    while True:
        desired: dict[str, Resource] = {}

        db = SessionLocal()
        try:
            rows = (
                db.query(Resource)
                .join(User, User.id == Resource.user_id)
                .filter(Resource.provider == "telegram")
                .filter(User.bot_enabled.is_(True))
                .all()
            )
            # включено только по status=active
            desired = {str(r.id): r for r in rows if r.status == "active"}
        finally:
            db.close()

        desired_ids = set(desired.keys())

        # Печатаем только когда набор активных ресурсов изменился
        if prev_desired_ids is None or desired_ids != prev_desired_ids:
            print(
                f"[BOT_WORKER] desired telegram active={len(desired_ids)} ids={sorted(desired_ids)}",
                flush=True,
            )
            prev_desired_ids = set(desired_ids)

        # OFF: останавливаем выключенные
        for rid in sorted(running - desired_ids):
            try:
                await session_registry.stop(rid)
                print(f"[BOT_WORKER] -OFF telegram rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram stop error rid={rid}: {e!r}", flush=True)
            finally:
                running.discard(rid)
                running_sig.pop(rid, None)

        # ON: запускаем новые
        for rid in sorted(desired_ids - running):
            try:
                await session_registry.ensure_started(desired[rid])
                print(f"[BOT_WORKER] +ON telegram rid={rid}", flush=True)
                running.add(rid)
                running_sig[rid] = _conf_sig(desired[rid])
            except Exception as e:
                print(f"[BOT_WORKER] telegram start error rid={rid}: {e!r}", flush=True)
                running.discard(rid)
                running_sig.pop(rid, None)

        # RESTART: если активный ресурс был сохранён (изменились label/meta_json) — перезапускаем
        for rid in sorted(desired_ids & running):
            try:
                new_sig = _conf_sig(desired[rid])
                old_sig = running_sig.get(rid)
                if old_sig and new_sig != old_sig:
                    await session_registry.stop(rid)
                    await session_registry.ensure_started(desired[rid])
                    running_sig[rid] = new_sig
                    print(f"[BOT_WORKER] ↻RESTART telegram rid={rid}", flush=True)
            except Exception as e:
                print(f"[BOT_WORKER] telegram restart error rid={rid}: {e!r}", flush=True)
                # если рестарт сломался — пусть следующий цикл попробует стартануть заново
                running.discard(rid)
                running_sig.pop(rid, None)

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
