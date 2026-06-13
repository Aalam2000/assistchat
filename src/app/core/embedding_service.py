"""
src/app/core/embedding_service.py
────────────────────────────────────────────────────────────
Генерация векторных эмбеддингов для сообщений.

Используется OpenAI text-embedding-3-small (1536 dims).
Ключ берётся из api_keys-ресурса пользователя — тенант-разделение гарантировано.
"""
from __future__ import annotations

from openai import AsyncOpenAI

EMBEDDING_MODEL = "text-embedding-3-small"


async def get_embedding(text: str, api_key: str) -> list[float] | None:
    """
    Возвращает вектор (1536 float) или None при пустом тексте / ошибке API.
    Никогда не бросает исключение — сообщение сохраняется в любом случае.
    """
    if not (text or "").strip():
        return None
    if not (api_key or "").strip():
        return None
    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text.strip(),
        )
        return resp.data[0].embedding
    except Exception as e:
        print(f"[EMBEDDING] get_embedding error: {e!r}")
        return None
