"""应用级设置：最近文件列表等（QSettings 持久化，跨会话保留）。"""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings

ORG_NAME = "RailLayout"
APP_NAME = "铁路配线图绘制器"
MAX_RECENT_FILES = 5


def _settings() -> QSettings:
    return QSettings(ORG_NAME, APP_NAME)


def instance() -> QSettings:
    """共享的 QSettings 实例（应用级设置/默认样式都存这里）。"""
    return _settings()


def recent_files() -> list[str]:
    value = _settings().value("recent_files", [])
    if isinstance(value, str):
        value = [value]
    return [str(p) for p in (value or [])][:MAX_RECENT_FILES]


def add_recent_file(path: str) -> None:
    items = [p for p in recent_files() if p != path]
    items.insert(0, path)
    settings = _settings()
    settings.setValue("recent_files", items[:MAX_RECENT_FILES])
    settings.setValue("last_directory", os.path.dirname(str(path)))


def remove_recent_file(path: str) -> None:
    settings = _settings()
    settings.setValue("recent_files", [p for p in recent_files() if p != path])


def clear_recent_files() -> None:
    _settings().setValue("recent_files", [])


def last_directory() -> str:
    return str(_settings().value("last_directory", "") or "")


def set_last_directory(path: str) -> None:
    _settings().setValue("last_directory", str(path))
