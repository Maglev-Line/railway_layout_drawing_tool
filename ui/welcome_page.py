"""欢迎页（空状态）：新建/打开工程入口与最近文件。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ui import theme

APP_SIGNATURE = "铁路配线图绘制器 v1.0 · PySide6"


class WelcomePage(QWidget):
    newRequested = Signal()
    openRequested = Signal()
    recentRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = QWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(12)
        layout.addStretch(1)

        title = QLabel("铁路配线图绘制器", self)
        title.setStyleSheet(theme.TITLE_QSS)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "绘制车站股道、道岔、站台与车挡：拉线成图、吸附对位、一键导出 PDF。", self
        )
        subtitle.setStyleSheet(theme.SUBTITLE_QSS)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        buttons = QWidget(self)
        button_layout = QVBoxLayout(buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_button = theme.big_button("新建工程", buttons)
        new_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        new_button.clicked.connect(self.newRequested.emit)
        open_button = theme.big_button("打开工程", buttons, outline=True)
        open_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        open_button.clicked.connect(self.openRequested.emit)
        button_layout.addWidget(new_button)
        button_layout.addWidget(open_button)
        layout.addWidget(buttons)

        hint = QLabel(
            "工程保存为 .rld 文件（JSON 明文），可随时打开继续编辑；意外退出后下次启动可恢复。",
            self,
        )
        hint.setStyleSheet(theme.HINT_QSS)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._recent_label = QLabel("最近打开", self)
        self._recent_label.setStyleSheet(theme.CARD_TITLE_QSS)
        self._recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._recent_label)

        self._recent_list = QListWidget(self)
        self._recent_list.setMaximumHeight(140)
        self._recent_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._recent_list.itemDoubleClicked.connect(self._on_recent_activated)
        self._recent_list.itemActivated.connect(self._on_recent_activated)
        layout.addWidget(self._recent_list, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        signature = QLabel(APP_SIGNATURE, self)
        signature.setStyleSheet(theme.FAINT_QSS)
        footer.addWidget(signature)
        layout.addLayout(footer)

        self.set_recent_files([])

    def set_recent_files(self, files: list[str]) -> None:
        self._recent_list.clear()
        for path in files:
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._recent_list.addItem(item)
        visible = bool(files)
        self._recent_label.setVisible(visible)
        self._recent_list.setVisible(visible)
        if visible:
            self._recent_list.setMinimumWidth(420)

    def _on_recent_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.recentRequested.emit(str(path))
