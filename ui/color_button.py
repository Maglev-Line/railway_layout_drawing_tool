"""颜色选择按钮：按钮本身就是色块 + 色值，点击弹取色器。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton

from ui import theme


class ColorButton(QPushButton):
    """统一的取色控件（属性面板与设置对话框共用）。"""

    colorChanged = Signal(str)

    def __init__(self, color: str, parent=None, title: str = "选择颜色"):
        super().__init__(parent)
        self._title = title
        self._color = QColor(str(color))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(96)
        self._sync()
        self.clicked.connect(self._pick)

    def color(self) -> str:
        return self._color.name()

    def set_color(self, color: str) -> None:
        candidate = QColor(str(color))
        if candidate.isValid():
            self._color = candidate
            self._sync()

    def _sync(self) -> None:
        name = self._color.name()
        text = theme.ACCENT_TEXT if self._color.lightness() < 140 else theme.GRAY_STRONG
        self.setText(name)
        self.setStyleSheet(
            f"background:{name};color:{text};border:1px solid {theme.BORDER};"
            "border-radius:4px;padding:2px 6px;min-width:88px;"
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(self._color, self, self._title)
        if chosen.isValid():
            self._color = chosen
            self._sync()
            self.colorChanged.emit(self.color())
