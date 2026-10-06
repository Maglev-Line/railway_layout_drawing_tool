"""入口级冒烟：主窗口可显示、事件循环可正常进出。"""
from __future__ import annotations

from PySide6.QtCore import QTimer

from core import autosave
from ui.main_window import MainWindow


def test_app_boot_and_quit(qapp, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    window = MainWindow()
    window.show()
    assert window.stack.currentWidget() is window.welcome

    QTimer.singleShot(50, qapp.quit)
    assert qapp.exec() == 0

    window.close()
