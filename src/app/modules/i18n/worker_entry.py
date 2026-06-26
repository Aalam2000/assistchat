"""Фоновый worker переводов (auto-i18n-lib), схема как в cargodb."""

from __future__ import annotations

import os
import time
from pathlib import Path

from autoi18n import Translator

from src.app.core.config import AUTO_I18N_TARGET_LANGS, SOURCE_LANG, TEMPLATES_DIR, TRANSLATIONS_DIR
from src.app.core.templates import template_to_page_key

DEFAULT_INTERVAL = int(os.getenv("AUTO_I18N_WORKER_INTERVAL", "300"))
DEFAULT_BATCH_SIZE = int(os.getenv("AUTO_I18N_WORKER_BATCH_SIZE", "50"))


def get_target_langs() -> list[str]:
    if not AUTO_I18N_TARGET_LANGS:
        raise RuntimeError(
            "AUTO_I18N_TARGET_LANGS не задан. "
            "Пример: AUTO_I18N_TARGET_LANGS=en,az,tr"
        )
    return [str(lang).strip() for lang in AUTO_I18N_TARGET_LANGS if str(lang).strip()]


def iter_template_files(templates_dir: Path) -> list[Path]:
    return sorted(templates_dir.rglob("*.html"))


def register_all_templates(translator: Translator, templates_dir: Path, target_langs: list[str]) -> list[str]:
    registered: list[str] = []

    for template_path in iter_template_files(templates_dir):
        rel_name = template_path.relative_to(templates_dir).as_posix()
        page_name = template_to_page_key(rel_name)

        def _make_getter(path: Path):
            def _getter() -> str:
                return path.read_text(encoding="utf-8")

            return _getter

        translator.register_page(
            page_name=page_name,
            html_getter=_make_getter(template_path),
            target_langs=target_langs,
        )
        registered.append(page_name)

    return registered


def run_once(batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    target_langs = get_target_langs()
    translator = Translator(
        cache_dir=str(TRANSLATIONS_DIR),
        source_lang=SOURCE_LANG,
        api_key=os.getenv("OPENAI_API_KEY", "local-no-key"),
    )

    registered_pages = register_all_templates(translator, TEMPLATES_DIR, target_langs)
    report = translator.process_all_translations(batch_size=batch_size)
    backend_report = translator.process_all_backend_key_translations(batch_size=batch_size)

    return {
        "pages": registered_pages,
        "html": report,
        "backend": backend_report,
    }


def run_loop(interval: int = DEFAULT_INTERVAL, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    print(
        f"[i18n-worker] started | interval={interval}s | batch_size={batch_size} | "
        f"target_langs={get_target_langs()}",
        flush=True,
    )

    while True:
        try:
            result = run_once(batch_size=batch_size)
            print(f"[i18n-worker] pages={len(result['pages'])} report={result['html']}", flush=True)
            if result["backend"]:
                print(f"[i18n-worker] backend={result['backend']}", flush=True)
        except KeyboardInterrupt:
            print("[i18n-worker] stopped", flush=True)
            break
        except Exception as exc:
            print(f"[i18n-worker] error: {exc}", flush=True)

        time.sleep(interval)


if __name__ == "__main__":
    run_loop()
