"""左侧绘制工具面板：按分组排列的互斥工具按钮（全部 NoFocus，避免抢空格/快捷键）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from graphics.tools import TOOL_GROUPS, TOOL_SPECS, ToolManager
from ui import icons, theme


class ToolPanel(QWidget):
    toolSelected = Signal(str)

    def __init__(self, manager: ToolManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        content = QWidget(self)
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        for group in TOOL_GROUPS:
            specs = [spec for spec in TOOL_SPECS if spec.group == group]
            if not specs:
                continue
            column.addWidget(self._group_label(group))
            for spec in specs:
                button = self._make_button(spec)
                column.addWidget(button)
                self._group.addButton(button)
                self._buttons[spec.tool_id] = button
        column.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        title = QLabel("绘制工具", self)
        title.setStyleSheet(theme.CARD_TITLE_QSS)
        hint = QLabel("左键绘制，右键/Esc 退回上一步；空格拖拽平移，Ctrl+滚轮缩放。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(scroll, 1)
        layout.addWidget(hint)

        manager.toolChanged.connect(self.sync)
        self.sync(manager.current_id())

    # ---------------- 构造 ----------------
    def _group_label(self, group: str) -> QLabel:
        label = QLabel(group, self)
        label.setStyleSheet(theme.GROUP_LABEL_QSS)
        return label

    def _make_button(self, spec) -> QToolButton:
        button = QToolButton(self)
        button.setText(spec.name)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIcon(icons.tool_icon(spec.tool_id))
        button.setIconSize(icons.icon_size())
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        keys = f"（{spec.shortcut}）" if spec.shortcut else ""
        button.setToolTip(f"{spec.name}{keys}：{spec.hint}")
        if spec.shortcut:
            button.setShortcut(spec.shortcut)
        button.clicked.connect(lambda _checked, tid=spec.tool_id: self.toolSelected.emit(tid))
        return button

    # ---------------- 同步 ----------------
    def sync(self, tool_id: str) -> None:
        button = self._buttons.get(tool_id)
        if button is None:
            return
        self._group.blockSignals(True)
        button.setChecked(True)
        self._group.blockSignals(False)
