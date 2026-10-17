"""右侧绘制指引面板：当前步骤提示 + 可作参照的既有元素（点击定位，自身不动）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from graphics.items.base import LayoutItem
from ui import theme

MAX_ROWS = 200  # 参照元素列表最多显示多少行，超出只提示数量
ANCHOR_PREFIX = "◆ "


def describe_item(item: LayoutItem) -> str:
    """一行文字描述元素：类型 + 可读内容/尺寸 + 编号。"""
    fields = {field.name for field in item.property_schema()}
    detail = ""
    if "text" in fields:
        content = str(item.get_prop("text") or "").strip()
        detail = f"「{content}」" if content else ""
    elif "length" in fields:
        detail = f"长 {float(item.get_prop('length')):.0f}"
    parts = [item.DISPLAY_NAME]
    if detail:
        parts.append(detail)
    parts.append(f"#{item.uid}")
    return " · ".join(parts)


class DrawingGuidePanel(QWidget):
    """绘制时引导用户：显示当前步骤、当前锚定到的元素、以及其余可参照元素。"""

    locateRequested = Signal(object)  # LayoutItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[LayoutItem] = []
        self._texts: list[str] = []
        self._rows: list[QListWidgetItem] = []
        self._anchor: LayoutItem | None = None

        title = QLabel("绘制指引", self)
        title.setStyleSheet(theme.CARD_TITLE_QSS)

        self._step = QLabel(self)
        self._step.setWordWrap(True)
        self._step.setStyleSheet(theme.HINT_QSS)

        self._anchor_label = QLabel(self)
        self._anchor_label.setWordWrap(True)

        self._list_title = QLabel(self)
        self._list_title.setStyleSheet(theme.GROUP_LABEL_QSS)

        self._list = QListWidget(self)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setUniformItemSizes(True)
        self._list.itemClicked.connect(self._on_row_clicked)
        self._list.itemActivated.connect(self._on_row_clicked)

        footer = QLabel("参照元素只用于对齐，不会被本次绘制移动。", self)
        footer.setWordWrap(True)
        footer.setStyleSheet(theme.FAINT_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(self._step)
        layout.addWidget(self._anchor_label)
        layout.addWidget(self._list_title)
        layout.addWidget(self._list, 1)
        layout.addWidget(footer)

        self.set_step("")
        self.set_anchor(None)
        self.set_items([])

    # ---------------- 内容 ----------------
    def set_step(self, text: str) -> None:
        """当前绘制步骤指引。"""
        self._step.setText(text or "—")

    def set_anchor(self, item: LayoutItem | None, detail: str = "") -> None:
        """当前锚定到的既有元素（None 表示未吸附到任何元素）。"""
        self._anchor = item
        if item is None:
            self._anchor_label.setText("当前锚定：—  把光标移到其它元素的股道/端点上即可对齐")
            self._anchor_label.setStyleSheet(theme.FAINT_QSS)
        else:
            suffix = f"（{detail}）" if detail else ""
            self._anchor_label.setText(f"{ANCHOR_PREFIX}当前锚定：{item.DISPLAY_NAME} #{item.uid}{suffix}")
            self._anchor_label.setStyleSheet(theme.ACCENT_HINT_QSS)
        self._apply_highlight()

    def set_items(self, items: list[LayoutItem]) -> None:
        """其余元素列表（图纸里所有可参照的既有元素）。"""
        items = list(items)
        if items == self._items:
            return
        self._items = items
        self._texts = [describe_item(item) for item in items]
        self._list.clear()
        self._rows = []
        for text, item in list(zip(self._texts, self._items))[:MAX_ROWS]:
            row = QListWidgetItem(text)
            row.setData(Qt.ItemDataRole.UserRole, item)
            row.setToolTip(f"{text}（点击在此图纸中定位）")
            self._list.addItem(row)
            self._rows.append(row)
        hidden = len(self._items) - len(self._rows)
        if hidden > 0:
            spare = QListWidgetItem(f"…还有 {hidden} 个元素未列出")
            spare.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(spare)
        count = len(self._items)
        self._list_title.setText(
            f"其余元素（固定不动）· {count}" if count else "其余元素（图纸里还没有其它元素）"
        )
        self._apply_highlight()

    # ---------------- 内部 ----------------
    def _apply_highlight(self) -> None:
        anchor = self._anchor
        for index, row in enumerate(self._rows):
            text = self._texts[index]
            is_anchor = anchor is not None and self._items[index] is anchor
            font = row.font()
            font.setBold(is_anchor)
            row.setFont(font)
            row.setForeground(QColor(theme.ACCENT if is_anchor else theme.GRAY_STRONG))
            row.setText(f"{ANCHOR_PREFIX}{text}" if is_anchor else text)

    def _on_row_clicked(self, row: QListWidgetItem) -> None:
        target = row.data(Qt.ItemDataRole.UserRole)
        if isinstance(target, LayoutItem):
            self.locateRequested.emit(target)
