from dataclasses import dataclass
from time import perf_counter
from typing import List, Dict, Any
import os

from openai import OpenAI

@dataclass
class Reply:
    text: str
    usage: Dict[str, int]
    latency_ms: int

class OpenAIChat:
    def __init__(self, settings: Dict[str, Any]):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=api_key)
        self.settings = settings

    def generate_reply(self, system_prompt: str, history: List[Dict[str, str]], user_text: str) -> Reply:
        """Синхронный вызов OpenAI Chat Completions."""
        start = perf_counter()
        messages = [{"role": "system", "content": system_prompt}] + history + [
            {"role": "user", "content": user_text}
        ]

        # таймаут из настроек
        timeout_sec = float(self.settings.get("timeouts", {}).get("request_sec", 20))
        client = self.client.with_options(timeout=timeout_sec)

        resp = client.chat.completions.create(
            model=self.settings.get("model", "gpt-4o-mini"),
            temperature=float(self.settings.get("temperature", 0.5)),
            max_tokens=int(self.settings.get("max_tokens_reply", 500)),
            messages=messages,
        )

        text = (resp.choices[0].message.content or "").strip()
        usage = {
            "tokens_in": getattr(resp.usage, "prompt_tokens", 0) or 0,
            "tokens_out": getattr(resp.usage, "completion_tokens", 0) or 0,
        }
        latency_ms = int((perf_counter() - start) * 1000)
        return Reply(text=text, usage=usage, latency_ms=latency_ms)
