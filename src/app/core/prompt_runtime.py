"""
src/app/core/prompt_runtime.py
─────────────────────────────────────────────────────────────────────────────
PROMPT runtime: извлекаем настройки из PROMPT-ресурса (resources.meta_json.prompt)
и собираем system_prompt для LLM.

Важно:
- history_pairs берём ИЗ PROMPT (как ты зафиксировал).
- Если history_pairs отсутствует (старые PROMPT), используем default=20.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _prompt_block(prompt_meta: Dict[str, Any] | None) -> Dict[str, Any]:
    meta = prompt_meta or {}
    p = meta.get("prompt") or {}
    return p if isinstance(p, dict) else {}


def get_history_pairs(prompt_meta: Dict[str, Any] | None, default: int = 20) -> int:
    p = _prompt_block(prompt_meta)
    raw = p.get("history_pairs", default)
    try:
        v = int(raw)
        return max(0, v)
    except Exception:
        return default


def get_google_source(prompt_meta: Dict[str, Any] | None) -> str:
    p = _prompt_block(prompt_meta)
    v = p.get("google_source") or ""
    return str(v).strip()


def get_examples(prompt_meta: Dict[str, Any] | None) -> List[Dict[str, str]]:
    p = _prompt_block(prompt_meta)
    ex = p.get("examples") or []
    if not isinstance(ex, list):
        return []
    out: List[Dict[str, str]] = []
    for item in ex:
        if not isinstance(item, dict):
            continue
        q = (item.get("q") or "").strip()
        a = (item.get("a") or "").strip()
        if q or a:
            out.append({"q": q, "a": a})
    return out


def build_system_prompt(
    prompt_meta: Dict[str, Any] | None,
    *,
    drive_context: str = "",
) -> str:
    """
    Собираем system_prompt из:
      - prompt.system_prompt
      - prompt.style_rules
      - prompt.examples
      - (опционально) drive_context (как вставка "knowledge")
    """
    p = _prompt_block(prompt_meta)

    system_prompt = (p.get("system_prompt") or "").strip()
    style_rules = (p.get("style_rules") or "").strip()
    examples = get_examples(prompt_meta)

    parts: List[str] = []
    if system_prompt:
        parts.append(system_prompt)
    if style_rules:
        parts.append(style_rules)

    if drive_context:
        dc = str(drive_context).strip()
        if dc:
            parts.append("KNOWLEDGE (from Google Drive):\n" + dc)

    if examples:
        lines: List[str] = ["EXAMPLES:"]
        for i, ex in enumerate(examples, start=1):
            q = (ex.get("q") or "").strip()
            a = (ex.get("a") or "").strip()
            if q:
                lines.append(f"{i}. Q: {q}")
            if a:
                lines.append(f"   A: {a}")
        parts.append("\n".join(lines))

    return "\n\n".join([x for x in parts if x]).strip()
