#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Интерактивный сбор метаданных проекта в JSON: tmp/project_report.json
Запускать ИЗ КОРНЯ проекта:  python tmp/project_probe.py
Можно запускать и прямо в PyCharm («Запустить текущий файл»).
"""

from __future__ import annotations
import re, sys, json, subprocess, configparser, datetime, ast
from pathlib import Path

def read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

# --- анализ кода ---
def analyze_python_file(path: Path, with_details: bool) -> dict:
    result = {}
    if not with_details:
        return result
    result = {"imports": [], "functions": []}
    try:
        text = read_text(path)
        if not text:
            return result
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    result["imports"].append(n.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for n in node.names:
                    result["imports"].append(f"{module}.{n.name}")
            elif isinstance(node, ast.FunctionDef):
                result["functions"].append(node.name)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result

# --- рекурсивный обход ---
def scan_dir(path: Path, expand_details: set[str], base: Path) -> list[dict]:
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
            entry["children"] = scan_dir(q, expand_details, base)
        else:
            if q.suffix == ".py":
                rel = str(q.relative_to(base).parts[0])
                entry.update(analyze_python_file(q, rel in expand_details))
        out.append(entry)
    return out

def resolve_project_root():
    cur = Path.cwd()
    for _ in range(6):
        if (cur / "docker-compose.yml").exists() or (cur / ".git").exists():
            return cur
        cur = cur.parent
    return Path.cwd()

# ---------- main ----------
def main():
    project_root = resolve_project_root()
    all_dirs = [d for d in sorted(project_root.iterdir()) if d.is_dir()]
    print("\nНайденные директории в корне проекта:")
    for i, d in enumerate(all_dirs, 1):
        print(f" {i}) {d.name}")
    choice = input("\nВведите номера директорий для включения (через запятую): ").strip()
    include_idxs = {int(x) for x in choice.split(",") if x.strip().isdigit()}
    include_dirs = [all_dirs[i - 1].name for i in include_idxs if 1 <= i <= len(all_dirs)]

    print("\nИз выбранных директорий разворачивать функции и импорты:")
    for i, d in enumerate(include_dirs, 1):
        print(f" {i}) {d}")
    choice2 = input("\nВведите номера директорий для разворачивания (через запятую): ").strip()
    expand_idxs = {int(x) for x in choice2.split(",") if x.strip().isdigit()}
    expand_dirs = {include_dirs[i - 1] for i in expand_idxs if 1 <= i <= len(include_dirs)}

    report_dir = project_root / "tmp"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "project_report.json"

    info = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root.resolve()),
        "fs": {},
    }

    for d in include_dirs:
        path = project_root / d
        info["fs"][d] = scan_dir(path, expand_dirs, project_root)

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Report written to {report_path}")

if __name__ == "__main__":
    main()
