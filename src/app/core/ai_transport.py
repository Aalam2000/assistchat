"""
src/app/core/ai_transport.py
────────────────────────────────────────────────────────────
ТОЛЬКО "AI-транспорт" (HTTP/SDK вызовы).

Задача:
- по key_field понять провайдера
- отправить messages -> получить text/usage
- (позже) добавить STT/TTS для провайдеров где нужно
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI


class AIProvider(str, Enum):
    openai = "openai"
    gemini = "gemini"
    anthropic = "anthropic"
    groq = "groq"           # openai-compatible
    deepseek = "deepseek"   # openai-compatible
    mistral = "mistral"     # openai-compatible
    xai = "xai"             # openai-compatible
    deepgram = "deepgram"   # сервис (STT), chat пока не трогаем
    unknown = "unknown"


OPENAI_COMPAT_BASE_URL: dict[AIProvider, str] = {
    AIProvider.groq: "https://api.groq.com/openai/v1",
    AIProvider.deepseek: "https://api.deepseek.com/v1",
    AIProvider.mistral: "https://api.mistral.ai/v1",
    AIProvider.xai: "https://api.x.ai/v1",
}

PROVIDER_BY_KEY_FIELD: dict[str, AIProvider] = {
    "creds.openai_api_key": AIProvider.openai,
    "creds.openai_admin_key": AIProvider.openai,
    "creds.gemini_api_key": AIProvider.gemini,
    "creds.anthropic_api_key": AIProvider.anthropic,
    "creds.groq_api_key": AIProvider.groq,
    "creds.deepseek_api_key": AIProvider.deepseek,
    "creds.mistral_api_key": AIProvider.mistral,
    "creds.xai_api_key": AIProvider.xai,
    "creds.deepgram_api_key": AIProvider.deepgram,
}


@dataclass(frozen=True)
class AIChatConfig:
    provider: AIProvider
    api_key: str
    model: str
    temperature: float = 0.7


@dataclass(frozen=True)
class AIChatResult:
    ok: bool
    text: str
    usage: Dict[str, Any]
    error: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


def provider_from_key_field(key_field: str) -> AIProvider:
    return PROVIDER_BY_KEY_FIELD.get((key_field or "").strip(), AIProvider.unknown)


async def chat(
    *,
    cfg: AIChatConfig,
    messages: List[Dict[str, str]],
) -> AIChatResult:
    """
    Единая точка для текстового чата.
    Сейчас реально работает:
      - OpenAI
      - OpenAI-compatible (groq/deepseek/mistral/xai)
    Остальные провайдеры — заглушки (эндпоинты заложены, наполним позже).
    """
    if not messages:
        return AIChatResult(ok=False, text="", usage={}, error="EMPTY_MESSAGES")

    if cfg.provider in {AIProvider.openai, AIProvider.groq, AIProvider.deepseek, AIProvider.mistral, AIProvider.xai}:
        base_url = OPENAI_COMPAT_BASE_URL.get(cfg.provider)  # None для openai
        client = AsyncOpenAI(api_key=cfg.api_key, base_url=base_url)
        try:
            resp = await client.chat.completions.create(
                model=cfg.model,
                temperature=cfg.temperature,
                messages=messages,
            )
            text = (resp.choices[0].message.content or "").strip()
            usage_obj = getattr(resp, "usage", None)
            usage = {
                "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0),
                "completion_tokens": int(getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0),
                "total_tokens": int(getattr(usage_obj, "total_tokens", 0) if usage_obj else 0),
                "provider": cfg.provider.value,
                "model": cfg.model,
            }
            return AIChatResult(ok=True, text=text, usage=usage, raw=None)
        except Exception as e:
            return AIChatResult(ok=False, text="", usage={"provider": cfg.provider.value, "model": cfg.model}, error=str(e))

    # Заглушки: провайдеры есть в keys, но реализацию добавим отдельными итерациями.
    if cfg.provider == AIProvider.gemini:
        return AIChatResult(ok=False, text="", usage={"provider": "gemini"}, error="NOT_IMPLEMENTED_GEMINI_CHAT")
    if cfg.provider == AIProvider.anthropic:
        return AIChatResult(ok=False, text="", usage={"provider": "anthropic"}, error="NOT_IMPLEMENTED_ANTHROPIC_CHAT")
    if cfg.provider == AIProvider.deepgram:
        return AIChatResult(ok=False, text="", usage={"provider": "deepgram"}, error="DEEPGRAM_IS_NOT_CHAT_PROVIDER_YET")

    return AIChatResult(ok=False, text="", usage={}, error="UNKNOWN_PROVIDER")
