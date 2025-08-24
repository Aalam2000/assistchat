#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает метаданные проекта в JSON: tmp/project_report.json
Запускать ИЗ КОРНЯ проекта:  python tmp/project_probe.py
"""

from __future__ import annotations
import os, re, sys, json, subprocess, configparser, datetime
from pathlib import Path

REPORT_DIR = Path("tmp")
REPORT_PATH = REPORT_DIR / "project_report.json"

# ---------- helpers ----------
def try_run(cmd: list[str], cwd: Path) -> tuple[int,str,str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"

def read_text(p: Path) -> str|None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

def list_dir(p: Path, max_items=200):
    out = []
    if not p.exists(): return out
    for q in sorted(p.iterdir()):
        try:
            out.append({
                "name": q.name,
                "is_dir": q.is_dir(),
                "size": None if q.is_dir() else q.stat().st_size,
            })
            if len(out) >= max_items: break
        except Exception:
            continue
    return out

def parse_requirements(req_path: Path):
    pkgs = []
    txt = read_text(req_path)
    if not txt: return pkgs
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        pkgs.append(s)
    return pkgs

def load_yaml(path: Path):
    # Пытаемся с PyYAML, иначе — простой парсер портов и имён
    try:
        import yaml  # type: ignore
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        # минимальный разбор service-имен и ports через regex в аварийном режиме
        data = {"services": {}}
        text = read_text(path) or ""
        current = None
        for line in text.splitlines():
            if line.strip().startswith(("#",";")): continue
            m = re.match(r"^\s{2}([A-Za-z0-9_.-]+):\s*$", line)
            if m:
                current = m.group(1)
                data["services"][current] = {}
                continue
            if current and "ports:" in line:
                data["services"][current].setdefault("ports", [])
            m2 = re.match(r"^\s*-\s*\"?(\d+:\d+)\"?\s*$", line)
            if current and m2:
                data["services"][current].setdefault("ports", []).append(m2.group(1))
        return data

def parse_env_file(path: Path):
    keys = []
    txt = read_text(path)
    if not txt: return keys
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        if "=" in s:
            k = s.split("=",1)[0].strip()
            if k: keys.append(k)
    return keys

def resolve_project_root():
    # ищем вверх docker-compose.yml или .git
    cur = Path.cwd()
    for _ in range(6):
        if (cur/"docker-compose.yml").exists() or (cur/".git").exists():
            return cur
        cur = cur.parent
    return Path.cwd()

def alembic_script_location(project_root: Path):
    ini = project_root/"alembic.ini"
    script_loc = None
    if ini.exists():
        cp = configparser.ConfigParser()
        cp.read(ini, encoding="utf-8")
        if cp.has_section("alembic") and cp.has_option("alembic","script_location"):
            script_loc = cp.get("alembic","script_location").strip()
    # по умолчанию — src/alembic, затем alembic
    if not script_loc:
        if (project_root/"src/alembic").exists():
            script_loc = "src/alembic"
        else:
            script_loc = "alembic"
    return script_loc, ini.exists()

def scan_migrations(versions_dir: Path):
    """
    Читает файлы миграций и извлекает revision/down_revision.
    Возвращает:
      - migrations: [{file, revision, down_revision}]
      - heads: список ревизий, на которые никто не ссылается
    """
    migs = []
    if not versions_dir.exists():
        return migs, []
    revs = set()
    downs = set()
    for p in sorted(versions_dir.glob("*.py")):
        txt = read_text(p) or ""
        rev = None
        down = None
        # Ищем по шаблону из файлов Alembic
        m1 = re.search(r"^revision\s*=\s*[\"']([\w\d]+)[\"']", txt, re.M|re.I)
        m2 = re.search(r"^down_revision\s*=\s*[\"']?([\w\d]+)?[\"']?", txt, re.M|re.I)
        if m1: rev = m1.group(1)
        if m2: down = m2.group(1) if m2.group(1) not in ("None","") else None
        if rev:
            migs.append({"file": p.name, "revision": rev, "down_revision": down})
            revs.add(rev)
            if down: downs.add(down)
    heads = sorted(revs - downs)
    return migs, heads

# ---------- main ----------
def main():
    project_root = resolve_project_root()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    info = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root.resolve()),
        "summary": {},
        "git": {},
        "python": {},
        "env": {},
        "docker_compose": {},
        "alembic": {},
        "fs": {},
        "warnings": [],
    }

    # summary
    info["summary"] = {
        "has_docker_compose": (project_root/"docker-compose.yml").exists(),
        "has_alembic_ini": (project_root/"alembic.ini").exists(),
        "has_src_app": (project_root/"src/app").exists(),
        "has_src_alembic": (project_root/"src/alembic").exists(),
        "requirements_txt": (project_root/"requirements.txt").exists(),
    }

    # git
    code, out, err = try_run(["git","rev-parse","--abbrev-ref","HEAD"], project_root)
    if code==0: info["git"]["branch"] = out
    code, out, err = try_run(["git","rev-parse","HEAD"], project_root)
    if code==0: info["git"]["last_commit"] = out
    code, out, err = try_run(["git","status","--porcelain"], project_root)
    if code==0: info["git"]["dirty"] = bool(out.strip())

    # python/requirements
    req_path = project_root/"requirements.txt"
    info["python"]["requirements"] = parse_requirements(req_path)

    # env
    env_file = project_root/".env"
    env_example = project_root/".env.example"
    info["env"][".env_keys"] = parse_env_file(env_file) if env_file.exists() else []
    info["env"][".env_example_keys"] = parse_env_file(env_example) if env_example.exists() else []
    info["env"]["present_files"] = [p for p in [".env",".env.example"] if (project_root/p).exists()]

    # docker-compose
    dc = project_root/"docker-compose.yml"
    if dc.exists():
        y = load_yaml(dc) or {}
        info["docker_compose"]["raw_keys"] = list(y.keys()) if isinstance(y, dict) else []
        services = {}
        for name, svc in (y.get("services") or {}).items():
            if not isinstance(svc, dict): continue
            services[name] = {
                "image": svc.get("image"),
                "build": svc.get("build"),
                "ports": svc.get("ports"),
                "env_file": svc.get("env_file"),
                "environment_keys": sorted(list((svc.get("environment") or {}).keys())) if isinstance(svc.get("environment"), dict) else svc.get("environment"),
                "volumes": svc.get("volumes"),
                "depends_on": svc.get("depends_on"),
            }
        info["docker_compose"]["services"] = services
    else:
        info["warnings"].append("docker-compose.yml not found")

    # alembic
    script_loc, has_ini = alembic_script_location(project_root)
    alembic_dir = project_root / script_loc
    versions_dir = alembic_dir / "versions"
    migs, heads = scan_migrations(versions_dir)
    info["alembic"] = {
        "script_location": script_loc,
        "alembic_ini_present": has_ini,
        "versions_dir_exists": versions_dir.exists(),
        "migrations_count": len(migs),
        "migrations": migs,
        "heads": heads,
    }

    # fs snapshots
    info["fs"] = {
        "src_app": list_dir(project_root/"src/app"),
        "src_alembic_versions": list_dir(versions_dir),
        "scripts": list_dir(project_root/"scripts"),
        "tmp": list_dir(project_root/"tmp"),
    }

    # write report
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"[OK] Report written to {REPORT_PATH}")

if __name__ == "__main__":
    sys.exit(main())
