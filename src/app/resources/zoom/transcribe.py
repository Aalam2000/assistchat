# src/app/resources/zoom/transcribe.py
import os
import json
from pathlib import Path
import requests

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


def _join_tokens(tokens: list[str]) -> str:
    """Аккуратно склеивает токены с учетом знаков препинания."""
    out: list[str] = []
    for tok in tokens:
        if not out:
            out.append(tok)
            continue
        # если токен начинается со знака препинания — лепим к предыдущему без пробела
        if tok[:1] in {".", ",", "!", "?", ":", ";", "…", ")", "»"}:
            out[-1] = out[-1] + tok
        # если токен — закрывающая кавычка/скобка — тоже без пробела
        elif tok in {")", "]", "}", "»"}:
            out[-1] = out[-1] + tok
        # если токен — открывающая кавычка/скобка — без пробела после нее
        elif tok in {"(", "[", "{", "«"}:
            out.append(tok)
        else:
            out.append(" " + tok)
    return "".join(out)


def transcribe_audio(file_path: str) -> str:
    """
    Транскрибирует аудио через Deepgram с диаризацией (RU)
    и возвращает текст с разделением по операторам.
    """
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY не найден в .env")

    audio_path = Path(file_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Файл не найден: {audio_path}")

    # Параметры распознавания:
    # - diarize=true: включаем диаризацию
    # - language=ru: русский
    # - smart_format/punctuate: удобная пунктуация/формат
    # - speaker_count=2: мягкая подсказка «два голоса» (если их больше — API может вернуть больше)
    params = {
        "model": "nova-2-general",
        "language": "ru",
        "diarize": "true",
        "smart_format": "true",
        "punctuate": "true",
        "speaker_count": "2",
    }

    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    # Отправляем файл и получаем JSON
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.deepgram.com/v1/listen",
            headers=headers,
            params=params,   # параметры в querystring
            files={"file": f}  # сам файл
        )
    resp.raise_for_status()
    data = resp.json()

    # Сохраняем «сырой» ответ для отладки
    raw_out = audio_path.with_suffix(audio_path.suffix + ".deepgram.json")
    try:
        with open(raw_out, "w", encoding="utf-8") as wf:
            json.dump(data, wf, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] не удалось сохранить raw JSON:", repr(e))

    # Разбор структуры Deepgram: results -> channels[0] -> alternatives[0]
    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
    except Exception as e:
        raise RuntimeError(f"Неожиданный ответ Deepgram, нет results/channels/alternatives: {repr(e)}")

    words = alt.get("words") or []
    if not words:
        # Диаризации нет — вернем цельный транскрипт
        txt = (alt.get("transcript") or "").strip()
        return txt

    # Группируем подряд идущие слова по одному и тому же speaker
    # и подписываем О1, О2, ...
    lines: list[str] = []
    cur_speaker = words[0].get("speaker", 0)
    buf: list[str] = []

    def speaker_label(s: int) -> str:
        # делаем человеческие индексы и кириллическую «О»
        try:
            idx = int(s)
        except Exception:
            idx = 0
        return f"О{idx + 1}"

    for w in words:
        sp = w.get("speaker", cur_speaker)
        tok = w.get("punctuated_word") or w.get("word") or ""
        tok = tok.strip()
        if sp != cur_speaker and buf:
            # закрываем предыдущую реплику
            text = _join_tokens(buf).strip()
            if text:
                lines.append(f"{speaker_label(cur_speaker)}: {text}")
            buf = []
            cur_speaker = sp
        if tok:
            buf.append(tok)

    # добиваем хвост
    if buf:
        text = _join_tokens(buf).strip()
        if text:
            lines.append(f"{speaker_label(cur_speaker)}: {text}")

    # Если по какой-то причине ничего не собрали — вернем общий transcript
    if not lines:
        return (alt.get("transcript") or "").strip()

    return "\n".join(lines)