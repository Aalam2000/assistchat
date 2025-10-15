"""
src/app/resources/telegram/openai_client.py
────────────────────────────────────────────
Модуль работы Telegram-ресурса с OpenAI API.

Назначение:
    • Унифицированная работа Telegram-агента с OpenAI (GPT, TTS, Whisper);
    • Учитывает системные и пользовательские ключи;
    • Поддерживает контекст диалога (историю сообщений);
    • Возвращает результат вместе с расходом токенов;
    • Безопасен для многопользовательской среды.
"""

import asyncio
import base64
import io
import os
from typing import Optional, Tuple, List, Dict, Any

import openai
from openai import AsyncOpenAI


# ────────────────────────────────────────────────────────────────
# ⚙️ Выбор API-ключа
# ────────────────────────────────────────────────────────────────
def get_api_key(user: Optional["User"] = None) -> str:
    """
    Возвращает API-ключ OpenAI:
    1. Если у пользователя есть персональный — берёт его (user.openai_api_key);
    2. Иначе системный из переменной окружения OPENAI_API_KEY;
    3. Если нет ни одного — бросает ошибку.
    """
    user_key = getattr(user, "openai_api_key", None)
    system_key = os.getenv("OPENAI_API_KEY", "") or openai.api_key

    api_key = user_key or system_key
    if not api_key:
        raise RuntimeError("[OpenAI] Не найден API-ключ: ни пользовательский, ни системный.")
    return api_key


class OpenAIClient:
    """
    Класс управления взаимодействием с OpenAI API.
    Поддерживает текст, голос, TTS и Whisper-распознавание.
    """

    def __init__(
            self,
            user: Optional["User"] = None,
            model_text: str = "gpt-4o-mini",
            model_tts: str = "gpt-4o-mini-tts",
            model_stt: str = "gpt-4o-mini-transcribe",
            temperature: float = 0.7,
            voice: str = "alloy",
            default_lang: str = "ru",
    ):
        """
        :param user: объект пользователя (для персонального ключа)
        :param model_text: модель для текстовых ответов
        :param model_tts:  модель для генерации голоса (TTS)
        :param model_stt:  модель для распознавания речи (Whisper)
        :param temperature: креативность ответов
        :param voice: тип голоса (alloy, verse, nova и т.п.)
        :param default_lang: язык по умолчанию
        """
        self.api_key = get_api_key(user)
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model_text = model_text
        self.model_tts = model_tts
        self.model_stt = model_stt
        self.temperature = temperature
        self.voice = voice
        self.default_lang = default_lang

    # ────────────────────────────────────────────────────────────────
    # 🧠 ТЕКСТОВЫЙ ДИАЛОГ С КОНТЕКСТОМ
    # ────────────────────────────────────────────────────────────────
    async def reply_text(
            self,
            prompt: str,
            system_prompt: Optional[str] = None,
            context: Optional[List[Dict[str, Any]]] = None,
            temperature: Optional[float] = None,
            model: Optional[str] = None,
    ) -> Tuple[str, int]:
        messages: List[Dict[str, Any]] = []

        if (system_prompt or "").strip():
            messages.append({"role": "system", "content": system_prompt.strip()})

        if context:
            for msg in context:
                role = (msg.get("role") or "user").strip()
                content = (msg.get("content") or "").strip()
                if content:
                    messages.append({"role": role, "content": content})

        # текущее сообщение пользователя — последним
        messages.append({"role": "user", "content": prompt})

        resp = await self.client.chat.completions.create(
            model=model or self.model_text,
            temperature=temperature if temperature is not None else self.temperature,
            messages=messages,
        )

        text = resp.choices[0].message.content.strip()
        usage = getattr(resp, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0

        return text, total_tokens

    # ────────────────────────────────────────────────────────────────
    # 🎤 РАСПОЗНАВАНИЕ ГОЛОСА (Speech-to-Text)
    # ────────────────────────────────────────────────────────────────
    async def transcribe_audio(self, audio_bytes: bytes, file_format: str = "ogg") -> str:
        file_obj = io.BytesIO(audio_bytes)
        file_obj.name = f"audio.{file_format}"

        resp = await self.client.audio.transcriptions.create(
            model=self.model_stt,
            file=file_obj,
            language=self.default_lang,
        )
        return resp.text.strip()

    # ────────────────────────────────────────────────────────────────
    # 🔊 ГЕНЕРАЦИЯ ГОЛОСА (Text-to-Speech)
    # ────────────────────────────────────────────────────────────────
    async def synthesize_speech(
            self,
            text: str,
            voice: Optional[str] = None,
            model: Optional[str] = None,
            format: str = "ogg",
    ) -> bytes:
        resp = await self.client.audio.speech.create(
            model=model or self.model_tts,
            voice=voice or self.voice,
            input=text,
            format=format,
        )
        if hasattr(resp, "data"):
            return base64.b64decode(resp.data[0].b64_json)
        if hasattr(resp, "content"):
            return resp.content
        raise RuntimeError("Не удалось получить аудиоданные")

    # ────────────────────────────────────────────────────────────────
    # ⚙️ Универсальный обработчик сообщений
    # ────────────────────────────────────────────────────────────────
    async def handle_message(
            self,
            text: Optional[str] = None,
            audio_bytes: Optional[bytes] = None,
            prefer_voice_reply: bool = False,
            system_prompt: Optional[str] = None,
            context: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        if audio_bytes:
            text = await self.transcribe_audio(audio_bytes)
            print(f"[OpenAI] Распознан текст: {text}")

        if not text:
            return {"text": "", "audio_bytes": None, "tokens": 0, "mode": "none"}

        reply_text, tokens = await self.reply_text(
            prompt=text,
            system_prompt=system_prompt,
            context=context,
        )

        if prefer_voice_reply:
            audio = await self.synthesize_speech(reply_text)
            return {
                "text": reply_text,
                "audio_bytes": audio,
                "tokens": tokens,
                "mode": "voice",
            }

        return {
            "text": reply_text,
            "audio_bytes": None,
            "tokens": tokens,
            "mode": "text",
        }

    # ────────────────────────────────────────────────────────────────
    # 🧩 Системные методы
    # ────────────────────────────────────────────────────────────────
    async def check_balance(self) -> dict:
        try:
            resp = await self.client.billing.usage()
            return {"ok": True, "data": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def models_list(self) -> list:
        resp = await self.client.models.list()
        return [m.id for m in resp.data]

    async def test_connection(self) -> bool:
        try:
            await self.models_list()
            return True
        except Exception:
            return False


# ────────────────────────────────────────────────────────────────
# 🔧 Пример использования
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def _demo():
        client = OpenAIClient()
        res = await client.handle_message("Привет, как дела?")
        print("Ответ:", res["text"], "| токены:", res["tokens"])


    asyncio.run(_demo())
