"""pytest 公共夹具：离屏 Qt 应用 + 隔离的 QSettings，避免污染本机设置。"""
from __future__ import annotations

import gc
import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import settings as app_settings  # noqa: E402

# 应用设置（最近打开/默认样式）全部落到临时 ini，测试不写真实注册表
_SETTINGS_DIR = tempfile.mkdtemp(prefix="rail_layout_settings_")
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.ini")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)


@pytest.fixture(scope="session", autouse=True)
def _isolated_app_settings():
    """core.settings.instance() 指向临时 ini（默认样式、最近文件都不会外泄）。"""
    handler = QSettings(_SETTINGS_FILE, QSettings.Format.IniFormat)
    original = app_settings.instance
    app_settings.instance = lambda: handler
    yield
    app_settings.instance = original


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _collect_qt_garbage():
    """每个用例结束后主动回收：Qt 图元/场景在应用存活时销毁，避免退出阶段踩堆。"""
    yield
    gc.collect()
