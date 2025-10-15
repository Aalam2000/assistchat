# src/app/resources/__init__.py
"""
Инициализация модуля ресурсов.
Автоматически импортирует подпапки (telegram, zoom, voice и т.д.),
чтобы при загрузке providers.py всё было доступно.
"""

import importlib
import pkgutil

for _, name, _ in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{name}")
