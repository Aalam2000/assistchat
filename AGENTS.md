# AGENTS.md
## Scope (редактируй только)
- src/**, tests/**, .github/workflows/**
- НЕ трогать: docker/prod/**, infra/**, scripts/production/**
## Env
- Build: docker compose -f docker-compose.yml -f docker-compose.dev.yml build
- Test: pytest -q && flake8 && mypy
## Правила
- Всегда новая ветка: codex/<slug>
- Добавляй/правь тесты, все тесты зелёные
- Без масштабных рефакторингов и ломающих API
- Коммиты в стиле Conventional Commits
