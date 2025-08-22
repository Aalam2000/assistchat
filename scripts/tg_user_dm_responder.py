# scripts/tg_user_dm_responder.py
import time
import os, sys, asyncio, uuid, re
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text as sql_text
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeAudio
from openai import OpenAI
from telethon.tl import types
from typing import cast
from openai.types.chat import ChatCompletionMessageParam

# В начало файла
_sessions = {}  # хранение статусов { phone: bool }

def toggle_session(phone: str) -> str:
    """
    Переключает состояние: если была активна -> выключает,
    если выключена -> запускает.
    Возвращает строку: "active" или "paused".
    """
    current = _sessions.get(phone, False)
    new_state = not current
    _sessions[phone] = new_state

    if new_state:
        print(f"[tg_user_dm_responder] Запуск сессии {phone}")
        # тут запуск (если нужен — у тебя уже есть логика)
    else:
        print(f"[tg_user_dm_responder] Остановка сессии {phone}")
        # тут остановка (если нужна логика)

    return "active" if new_state else "paused"

async def _resolve_peer(tg, peer_id: int):
    try:
        return await tg.get_input_entity(types.PeerUser(peer_id))
    except Exception:
        # на всякий случай прогреем ещё раз и повторим
        async for _ in tg.iter_dialogs():
            pass
        return await tg.get_input_entity(types.PeerUser(peer_id))

load_dotenv()

STYLE_PROFILE_PATH = os.getenv("STYLE_PROFILE_PATH", "/app/branding/style_profile.md")

def read_style_text() -> str:
    try:
        with open(STYLE_PROFILE_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def enforce_style(text: str) -> str:
    """Чистим дежурные хвосты и приводим к требуемому завершению."""
    if not text:
        return text
    t = re.sub(r"\s+", " ", text).strip()

    # режем типичные завершающие штампы в конце ответа
    banned_tail_patterns = [
        r"если\s+.*вопрос(ы|ов)?.{0,40}(дайте\s+знать|обращайтесь|пишите).*",
        r"обращайтесь.*",
        r"пишите.*если.*что.*",
        r"я\s+здесь.*помочь.*",
        r"спасибо.*",
        r"хорошего\s+дня.*",
    ]
    for pat in banned_tail_patterns:
        t = re.sub(rf"(?:\s*[.!?])?\s*({pat})\s*$", "", t, flags=re.IGNORECASE)

    # добавим финальную точку, если совсем без знака
    if not re.search(r"[.!?]$", t):
        t += "."
    return t.strip()


def env_or_fail(k: str) -> str:
    v = os.getenv(k)
    if not v:
        print(f"[ERROR] missing env {k}", file=sys.stderr); sys.exit(1)
    return v

def db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url: return url
    user = env_or_fail("DB_USER"); pwd = env_or_fail("DB_PASSWORD")
    host = os.getenv("DB_HOST", "db"); port = os.getenv("DB_PORT", "5432")
    name = env_or_fail("DB_NAME")
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"

def load_history(eng, account_id, peer_id, limit: int):
    q = sql_text("""
        SELECT direction, msg_type, text
        FROM messages
        WHERE account_id = :acc AND peer_id = :peer AND msg_type IN ('text','voice')
        ORDER BY created_at DESC
        LIMIT :lim
    """)
    with eng.begin() as conn:
        rows = conn.execute(q, {"acc": account_id, "peer": peer_id, "lim": limit}).mappings().all()
    rows = list(reversed(rows))
    chat_msgs = []
    for r in rows:
        t = (r["text"] or "").strip()
        if not t: continue
        role = "user" if r["direction"] == "in" else "assistant"
        chat_msgs.append({"role": role, "content": t})
    return chat_msgs

def is_voice_message(msg) -> bool:
    try:
        doc = getattr(msg, "document", None)
        if not doc or not getattr(doc, "attributes", None): return False
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeAudio) and getattr(attr, "voice", False):
                return True
        # некоторые клиенты шлют voice как "обычный аудио"; тоже считаем как голос
        return any(isinstance(attr, DocumentAttributeAudio) for attr in doc.attributes)
    except Exception:
        return False

async def transcribe_if_needed(
    ai: OpenAI,
    tg_msg,
    tmp_dir: Path,
    stt_model: str
) -> tuple[str, str] | None:
    """
    Возвращает (text, msg_type). Если сообщение голосовое — расшифровывает через Whisper.
    msg_type: 'text' или 'voice'
    """
    raw_text = (tg_msg.message or "").strip()
    if raw_text and not getattr(tg_msg, "media", None):
        return raw_text, "text"

    # голос?
    if is_voice_message(tg_msg):
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = await tg_msg.download_media(file=str(tmp_dir / f"in_{tg_msg.id}"))
        try:
            with open(path, "rb") as f:
                tr = ai.audio.transcriptions.create(model=stt_model, file=f)
            text = (getattr(tr, "text", "") or "").strip()
            return text or "[voice message]", "voice"
        finally:
            try: os.remove(path)
            except Exception: pass

    # любое другое медиа — не обрабатываем (можно расширить позже)
    return raw_text or "[unsupported message]", "text"

async def main():
    # ENV
    phone = env_or_fail("TELEGRAM_PHONE_NUMBER")
    client_ai = OpenAI(api_key=env_or_fail("OPENAI_API_KEY"))
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    history_limit = int(os.getenv("HISTORY_LIMIT", "20"))
    reply_voice = (os.getenv("REPLY_VOICE", "true").strip().lower() in {"1","true","yes"})
    stt_model = os.getenv("STT_MODEL", "whisper-1")
    tts_model = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
    tts_voice = os.getenv("TTS_VOICE", "alloy")
    tts_format = os.getenv("TTS_FORMAT", "mp3")
    tmp_dir = Path(os.getenv("TMP_DIR", "/app/tmp"))

    style_text = read_style_text()
    print(f"[INFO] style profile loaded: {STYLE_PROFILE_PATH} ({len(style_text)} chars)")

    system_prompt = (
            "Ты — вежливый ассистент-разработчика ПО. Отвечай кратко и по делу, "
            "на том же языке, что и пользователь. Если идёт разговор про заказ разработки — "
            "предложи короткий план и предложи созвон.\n\n"
            "СОБЛЮДАЙ СЛЕДУЮЩИЙ СТИЛЬ (если не пуст):\n"
            + style_text
    )

    # DB
    eng = create_engine(db_url(), future=True)
    q_acc = sql_text("""
                     SELECT id, app_id, app_hash, string_session
                     FROM tg_accounts
                     WHERE phone_e164 = :phone
                       AND status = 'active'
                       AND length(string_session) > 0 LIMIT 1
                     """)

    row = None
    while not row:
        with eng.begin() as conn:
            row = conn.execute(q_acc, {"phone": phone}).mappings().first()
        if not row:
            print("[WARN] Active account with session not found. Waiting for activation...")
            time.sleep(10)

    account_id = row["id"]
    api_id = int(row["app_id"])
    api_hash = row["app_hash"]
    session_str = row["string_session"]

    # Telegram
    tg = TelegramClient(StringSession(session_str), api_id, api_hash)
    await tg.connect()
    # прогрев диалогов, чтобы "закешировать" InputEntity пользователей
    warm = 0
    async for _ in tg.iter_dialogs():
        warm += 1
    print(f"[INFO] dialogs cache warmed: {warm}")
    me = await tg.get_me()
    print(f"[INFO] Logged in as @{getattr(me,'username', None)} (id={getattr(me,'id', None)}). DM responder is running (voice enabled={reply_voice})...")

    @tg.on(events.NewMessage(incoming=True))
    async def on_new_dm(event: events.NewMessage.Event):
        try:
            if not event.is_private or event.out:
                return

            msg = event.message
            telegram_msg_id = int(msg.id)
            peer_id = int(event.sender_id or 0)
            now = datetime.now(timezone.utc)

            # --- STT / текст сообщения + тип ---
            text_in, msg_type_in = await transcribe_if_needed(client_ai, msg, tmp_dir, stt_model)

            # антидубль
            sql_seen = sql_text("""
                INSERT INTO updates_seen (account_id, chat_id, message_id)
                VALUES (:acc, :chat, :mid)
                ON CONFLICT DO NOTHING
                RETURNING 1
            """)
            with eng.begin() as conn:
                inserted = conn.execute(sql_seen, {"acc": account_id, "chat": peer_id, "mid": telegram_msg_id}).first()
            if not inserted:
                return

            # лог входящего
            sql_in = sql_text("""
                INSERT INTO messages (id, account_id, peer_id, peer_type, chat_id, msg_id,
                                      direction, msg_type, text, created_at)
                VALUES (:id, :acc, :peer, 'user', :chat, :mid, 'in', :mtype, :text, :now)
            """)
            with eng.begin() as conn:
                conn.execute(sql_in, {
                    "id": str(uuid.uuid4()), "acc": account_id, "peer": peer_id,
                    "chat": peer_id, "mid": telegram_msg_id,
                    "mtype": msg_type_in, "text": text_in, "now": now
                })
            print(f"[IN/{msg_type_in}] from {peer_id}: {text_in[:80]!r} (msg_id={telegram_msg_id})")

            # История + LLM
            history_msgs = load_history(eng, account_id, peer_id, history_limit)
            messages_payload = [{"role":"system","content":system_prompt}] + history_msgs + [
                {"role":"user","content": text_in}
            ]

            t0 = datetime.now(timezone.utc)
            try:
                resp = client_ai.chat.completions.create(
                    model=model_name,
                    messages=cast(list[ChatCompletionMessageParam], messages_payload),
                    temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
                    max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "300")),
                )
                answer = (resp.choices[0].message.content or "").strip()
                answer = enforce_style(answer)
            except Exception as e:
                answer = "Извини, сейчас не могу ответить по сути. Давай попробуем чуть позже."
                answer = enforce_style(answer)
                print(f"[WARN] OpenAI error: {e}", file=sys.stderr)
            latency_ms = int((datetime.now(timezone.utc) - t0).total_seconds()*1000)

            # --- настройки ответа ---
            reply_text_always = (os.getenv("REPLY_TEXT_ALWAYS", "false").strip().lower() in {"1", "true", "yes"})

            # --- если вход был НЕ voice ИЛИ голос выключен -> обычный текст ---
            if (msg_type_in != "voice") or (not reply_voice):
                dest = await _resolve_peer(tg, peer_id)
                sent_text = await tg.send_message(dest, answer)
                out_text_msg_id = int(getattr(sent_text, "id", 0))
                sql_out = sql_text("""
                                   INSERT INTO messages (id, account_id, peer_id, peer_type, chat_id, msg_id,
                                                         direction, msg_type, text, latency_ms, created_at)
                                   VALUES (:id, :acc, :peer, 'user', :chat, :mid, 'out', :mtype, :text, :lat, :now)
                                   """)
                with eng.begin() as conn:
                    conn.execute(sql_out, {
                        "id": str(uuid.uuid4()), "acc": account_id, "peer": peer_id, "chat": peer_id,
                        "mid": out_text_msg_id, "mtype": "text", "text": answer,
                        "lat": latency_ms, "now": datetime.now(timezone.utc),
                    })
                print(f"[OUT/text] to {peer_id}: {answer[:80]!r} (msg_id={out_text_msg_id})  [LLM {latency_ms} ms]")

            # --- если вход был VOICE и голос включен -> voice-note; текст дублируем ТОЛЬКО если включён флаг ---

                print(f"[DEBUG] want_voice={(msg_type_in == 'voice') and reply_voice} (msg_type_in={msg_type_in}, reply_voice={reply_voice})")

            else:
                # по желанию сначала отправим текст (если нужно дублирование)
                out_text_msg_id = None
                if reply_text_always:
                    sent_text = await tg.send_message(peer_id, answer or "Ок.")
                    out_text_msg_id = int(getattr(sent_text, "id", 0))
                    sql_out = sql_text("""
                                       INSERT INTO messages (id, account_id, peer_id, peer_type, chat_id, msg_id,
                                                             direction, msg_type, text, latency_ms, created_at)
                                       VALUES (:id, :acc, :peer, 'user', :chat, :mid, 'out', :mtype, :text, :lat, :now)
                                       """)
                    with eng.begin() as conn:
                        conn.execute(sql_out, {
                            "id": str(uuid.uuid4()), "acc": account_id, "peer": peer_id, "chat": peer_id,
                            "mid": out_text_msg_id, "mtype": "text", "text": answer,
                            "lat": latency_ms, "now": datetime.now(timezone.utc),
                        })
                    print(f"[OUT/text] to {peer_id}: {answer[:80]!r} (msg_id={out_text_msg_id})  [LLM {latency_ms} ms]")

                # генерим аудио TTS -> mp3
                tmp_dir.mkdir(parents=True, exist_ok=True)
                mp3_path = tmp_dir / f"out_{peer_id}_{telegram_msg_id}.mp3"
                ogg_path = tmp_dir / f"out_{peer_id}_{telegram_msg_id}.ogg"

                try:
                    speech = client_ai.audio.speech.create(
                        model=tts_model,
                        voice=tts_voice,
                        input=answer,
                    )
                    content = getattr(speech, "content", None)
                    if content is None and hasattr(speech, "to_bytes"):
                        content = speech.to_bytes()
                    if not content:
                        raise RuntimeError("TTS returned empty content")
                    with open(mp3_path, "wb") as f:
                        f.write(content)

                    # mp3 -> ogg/opus voice-note (кружочек)
                    import subprocess as sp
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(mp3_path),
                        "-c:a", "libopus",
                        "-b:a", "48k",
                        "-ac", "1",
                        "-ar", "48000",
                        "-vbr", "on",
                        "-compression_level", "10",
                        "-application", "voip",
                        str(ogg_path),
                    ]
                    sp.run(cmd, check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

                    # отправляем как voice-note (кружок) c атрибутом voice
                    import subprocess as sp
                    from telethon.tl.types import DocumentAttributeAudio

                    # посчитаем длительность ogg (в секундах)
                    try:
                        dur_str = sp.check_output([
                            "ffprobe", "-v", "error",
                            "-select_streams", "a:0",
                            "-show_entries", "stream=duration",
                            "-of", "default=nokey=1:noprint_wrappers=1",
                            str(ogg_path),
                        ]).decode().strip()
                        duration = max(1, int(round(float(dur_str or "0"))))
                    except Exception:
                        duration = 1  # безопасный дефолт

                    # отправляем как voice-note (кружочек)
                    dest = await _resolve_peer(tg, peer_id)
                    sent_voice = await tg.send_file(dest, str(ogg_path), voice_note=True)

                    out_voice_msg_id = int(getattr(sent_voice, "id", 0))

                    # логируем исходящее как VOICE (текст ответа сохраняем как расшифровку)
                    sql_out = sql_text("""
                                       INSERT INTO messages (id, account_id, peer_id, peer_type, chat_id, msg_id,
                                                             direction, msg_type, text, latency_ms, created_at)
                                       VALUES (:id, :acc, :peer, 'user', :chat, :mid, 'out', :mtype, :text, :lat, :now)
                                       """)
                    with eng.begin() as conn:
                        conn.execute(sql_out, {
                            "id": str(uuid.uuid4()), "acc": account_id, "peer": peer_id, "chat": peer_id,
                            "mid": out_voice_msg_id, "mtype": "voice", "text": answer,
                            "lat": latency_ms, "now": datetime.now(timezone.utc),
                        })
                    print(f"[OUT/voice] to {peer_id}: (msg_id={out_voice_msg_id})")

                except Exception as e:
                    # голос дополнительный; если отключено дублирование, текст уже НЕ отправляли — подстрахуемся
                    print(f"[WARN] voice-note failed, sending text fallback: {e}", file=sys.stderr)
                    if not reply_text_always:
                        sent_text = await tg.send_message(peer_id, answer or "Ок.")
                        out_text_msg_id = int(getattr(sent_text, "id", 0))
                        sql_out = sql_text("""
                                           INSERT INTO messages (id, account_id, peer_id, peer_type, chat_id, msg_id,
                                                                 direction, msg_type, text, latency_ms, created_at)
                                           VALUES (:id, :acc, :peer, 'user', :chat, :mid, 'out', :mtype, :text, :lat,
                                                   :now)
                                           """)
                        with eng.begin() as conn:
                            conn.execute(sql_out, {
                                "id": str(uuid.uuid4()), "acc": account_id, "peer": peer_id, "chat": peer_id,
                                "mid": out_text_msg_id, "mtype": "text", "text": answer,
                                "lat": latency_ms, "now": datetime.now(timezone.utc),
                            })
                        print(f"[OUT/text-FALLBACK] to {peer_id}: {answer[:80]!r} (msg_id={out_text_msg_id})")
                finally:
                    try:
                        if mp3_path.exists(): os.remove(mp3_path)
                        if ogg_path.exists(): os.remove(ogg_path)
                    except Exception:
                        pass



        except Exception as e:
            print(f"[WARN] handler error: {e}", file=sys.stderr)

    await tg.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] stopped by user"); sys.exit(0)
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr) # sys.exit(2)
