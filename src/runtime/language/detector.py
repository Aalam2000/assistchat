from typing import List
import langid

langid.set_languages(["ru", "az", "en"])  # ограничим пространство

def detect(text: str, supported: List[str], fallback: str) -> str:
    """Определяет язык из supported, иначе возвращает fallback."""
    try:
        code, _ = langid.classify(text or "")
        return code if code in supported else fallback
    except Exception:
        return fallback
