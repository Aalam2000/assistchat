#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор информации по HTML/CSS/JS: tmp/project_report.json
Запускать ИЗ КОРНЯ проекта:  python tmp/project_probe.py
"""

from __future__ import annotations
import re, json, datetime
from pathlib import Path

def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

def analyze_web_file(path: Path) -> dict:
    result: dict[str, list[str]] = {}
    text = read_text(path)
    if not text:
        return result

    if path.suffix.lower() in {".html", ".htm", ".jinja", ".jinja2"}:
        css_links = re.findall(r'<link[^>]+href=["\']([^"\']+\.css)["\']', text, flags=re.I)
        js_links = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', text, flags=re.I)
        result["css_used"] = sorted(set(css_links))
        result["js_used"] = sorted(set(js_links))
    return result

def scan_dir(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for q in sorted(path.iterdir()):
        entry = {
            "name": q.name,
            "is_dir": q.is_dir(),
            "size": None if q.is_dir() else q.stat().st_size,
        }
        if q.is_dir():
            entry["children"] = scan_dir(q)
        else:
            if q.suffix.lower() in {".html", ".htm", ".jinja", ".jinja2", ".css", ".js"}:
                entry.update(analyze_web_file(q))
        out.append(entry)
    return out

def resolve_project_root():
    cur = Path.cwd()
    for _ in range(6):
        if (cur / "docker-compose.yml").exists() or (cur / ".git").exists():
            return cur
        cur = cur.parent
    return Path.cwd()

def main():
    project_root = resolve_project_root()
    report_dir = project_root / "tmp"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "project_report.json"

    info = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root.resolve()),
        "fs": {}
    }

    # фиксированные директории
    for d in ["src/app/templates", "src/app/static"]:
        path = project_root / d
        if path.exists():
            info["fs"][d] = scan_dir(path)

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"[OK] Report written to {report_path}")

if __name__ == "__main__":
    main()
