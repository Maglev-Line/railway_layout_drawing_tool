"""工作页：控制行 + 工具面板 + 画布 + 属性面板。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core import registry
from core.commands import AddItemsCommand, EditPropertiesCommand, RemoveItemsCommand
from core.model import Document
from graphics.items.base import LayoutItem
from graphics.scene import LayoutScene
from graphics.tools import ToolManager
from ui.canvas_view import CanvasView
from ui.property_panel import ANGLE_STEP_CHOICES, FOCUS_FIELD_ORDER, PropertyPanel
from ui.tool_panel import ToolPanel

PASTE_OFFSET = 10.0
NUDGE_FINE = 1.0
ROTATE_STEP_DEFAULT = 15.0


class EditorPage(QWidget):
    """画布工作区；文档可整体切换（新建/打开/恢复）。"""

    statusMessage = Signal(str)
    cursorMoved = Signal(QPointF)
    zoomChanged = Signal(float)
    toolChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Document | None = None
        self._scene: LayoutScene | None = None
        self._clipboard: list[dict] = []

        self.view = CanvasView(self)
        self.tool_manager = ToolManager(self.view, self)
        self.view.set_tool_manager(self.tool_manager)
        self.tool_manager.message.connect(self.statusMessage.emit)

        self.tool_panel = ToolPanel(self.tool_manager, self)
        self.property_panel = PropertyPanel(self)

        controls = QWidget(self)
        row = QHBoxLayout(controls)
        row.setContentsMargins(6, 6, 6, 0)
        row.setSpacing(9)
        row.addWidget(QLabel("角度吸附："))
        self._angle_combo = QComboBox(controls)
        for step, label in ANGLE_STEP_CHOICES:
            self._angle_combo.addItem(label, step)
        self._angle_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._angle_combo.currentIndexChanged.connect(self._on_angle_step_changed)
        row.addWidget(self._angle_combo)
        self._snap_grid_check = QCheckBox("网格吸附", controls)
        self._snap_grid_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._snap_grid_check.toggled.connect(self._on_snap_grid_changed)
        row.addWidget(self._snap_grid_check)
        self._show_grid_check = QCheckBox("显示网格", controls)
        self._show_grid_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._show_grid_check.toggled.connect(self._on_show_grid_changed)
        row.addWidget(self._show_grid_check)
        self._paper_check = QCheckBox("纸张边框", controls)
        self._paper_check.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._paper_check.toggled.connect(self._on_paper_frame_changed)
        row.addWidget(self._paper_check)
        row.addStretch(1)
        fit_button = QPushButton("适配窗口", controls)
        fit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fit_button.clicked.connect(self.view.fit_to_content)
        row.addWidget(fit_button)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.tool_panel)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.property_panel)
        right.setMinimumWidth(280)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(left)
        self._splitter.addWidget(self.view)
        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([190, 900, 300])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(controls)
        layout.addWidget(self._splitter, 1)

        self.tool_panel.toolSelected.connect(self.tool_manager.set_tool)
        self.tool_manager.toolChanged.connect(self._on_tool_changed)
        self.view.zoomChanged.connect(self.zoomChanged.emit)
        self.view.cursorMoved.connect(self.cursorMoved.emit)
        self.property_panel.deleteRequested.connect(self.delete_selected)

    # ---------------- 文档 ----------------
    def document(self) -> Document | None:
        return self._document

    def scene(self) -> LayoutScene | None:
        return self._scene

    def set_document(self, document: Document, items: list[LayoutItem] | None = None) -> None:
        old_scene = self._scene
        if old_scene is not None:
            self._disconnect_scene(old_scene)
            self.view.setScene(None)

        scene = LayoutScene(document, self)
        scene.textEditRequested.connect(self._on_edit_requested)
        self._scene = scene
        self._document = document
        self.view.setScene(scene)
        self.tool_manager.set_context(scene, document)
        self.property_panel.set_context(scene, document)
        if items:
            for item in items:
                scene.addItem(item)
            scene.notify_items_changed(items)
        document.settingsChanged.connect(self._sync_controls)
        self._sync_controls()
        self.view.fit_to_content()

    def reload_document(self, document: Document, items: list[LayoutItem] | None = None) -> None:
        """包装 set_document，避免重复连接旧信号。"""
        if self._document is not None:
            try:
                self._document.settingsChanged.disconnect(self._sync_controls)
            except (RuntimeError, TypeError):
                pass
        self.set_document(document, items)

    def _disconnect_scene(self, scene: LayoutScene) -> None:
        try:
            scene.textEditRequested.disconnect(self._on_edit_requested)
        except (RuntimeError, TypeError):
            pass

    def _on_edit_requested(self, item: LayoutItem) -> None:
        names = {field.name for field in item.property_schema()}
        target = next((name for name in FOCUS_FIELD_ORDER if name in names), "")
        self.property_panel.focus_field(target)

    # ---------------- 控制行 ----------------
    def _sync_controls(self, *_args) -> None:
        document = self._document
        if document is None:
            return
        for widget in (self._angle_combo, self._snap_grid_check, self._show_grid_check, self._paper_check):
            widget.blockSignals(True)
        index = self._angle_combo.findData(document.angle_step)
        if index >= 0:
            self._angle_combo.setCurrentIndex(index)
        self._snap_grid_check.setChecked(document.snap_grid)
        self._show_grid_check.setChecked(document.show_grid)
        self._paper_check.setChecked(document.paper.show_frame)
        for widget in (self._angle_combo, self._snap_grid_check, self._show_grid_check, self._paper_check):
            widget.blockSignals(False)

    def _on_angle_step_changed(self, index: int) -> None:
        if self._document is None:
            return
        self._document.angle_step = float(self._angle_combo.itemData(index))
        self._document.notify_settings_changed()

    def _on_snap_grid_changed(self, checked: bool) -> None:
        if self._document is None:
            return
        self._document.snap_grid = bool(checked)
        self._document.notify_settings_changed()

    def _on_show_grid_changed(self, checked: bool) -> None:
        if self._document is None:
            return
        self._document.show_grid = bool(checked)
        self._document.notify_settings_changed()
        if self._scene is not None:
            self._scene.update()

    def _on_paper_frame_changed(self, checked: bool) -> None:
        if self._document is None:
            return
        self._document.paper.show_frame = bool(checked)
        self._document.notify_settings_changed()
        if self._scene is not None:
            self._scene.refresh_paper()

    # ---------------- 工具 ----------------
    def _on_tool_changed(self, tool_id: str) -> None:
        self.toolChanged.emit(tool_id)

    def cancel_tool(self) -> None:
        self.tool_manager.cancel()

    def finish_chain(self) -> None:
        self.tool_manager.finish_chain()

    # ---------------- 编辑操作 ----------------
    def _selected_items(self) -> list[LayoutItem]:
        if self._scene is None:
            return []
        return [item for item in self._scene.selectedItems() if isinstance(item, LayoutItem)]

    def _push(self, command) -> None:
        if self._document is not None:
            self._document.undo_stack.push(command)

    def apply_style(self, style) -> str:
        """把默认样式套到当前图纸已有元素（一次撤销步骤），返回提示文本。"""
        from graphics import style as style_module

        scene, document = self._scene, self._document
        if scene is None or document is None:
            return "还没有打开图纸"
        items = [item for item in scene.layout_items() if item.is_printable()]
        entries = style_module.restyle_entries(items, style)
        if not entries:
            return "当前图纸没有需要更新的元素"
        self._push(EditPropertiesCommand(scene, entries, "应用默认样式"))
        return f"已按新样式更新 {len(entries)} 个元素（Ctrl+Z 可撤销）"

    def delete_selected(self) -> None:
        items = self._selected_items()
        if not items or self._scene is None:
            return
        self._push(RemoveItemsCommand(self._scene, items, "删除元素"))
        self.statusMessage.emit(f"已删除 {len(items)} 个元素（Ctrl+Z 可撤销）")

    def select_all(self) -> None:
        if self._scene is None:
            return
        for item in self._scene.layout_items():
            item.setSelected(True)

    def copy_selected(self) -> None:
        items = self._selected_items()
        if not items:
            return
        self._clipboard = [item.to_dict() for item in items]
        self.statusMessage.emit(f"已复制 {len(items)} 个元素")

    def paste(self) -> None:
        if not self._clipboard or self._scene is None:
            return
        items = []
        for data in self._clipboard:
            payload = dict(data)
            payload["id"] = ""
            payload["x"] = float(data.get("x", 0.0)) + PASTE_OFFSET
            payload["y"] = float(data.get("y", 0.0)) + PASTE_OFFSET
            try:
                item = registry.create_element(payload)
            except KeyError:
                continue
            items.append(item)
        if not items:
            return
        for item in items:
            self._scene.addItem(item)
        self._push(AddItemsCommand(self._scene, items, "粘贴"))
        self._scene.clearSelection()
        for item in items:
            item.setSelected(True)

    def duplicate_selected(self) -> None:
        self.copy_selected()
        self.paste()

    def nudge_selected(self, dx: float, dy: float) -> None:
        items = self._selected_items()
        if not items or self._scene is None or self._document is None:
            return
        entries = []
        for item in items:
            old_x, old_y = item.pos().x(), item.pos().y()
            item.setPos(old_x + dx, old_y + dy)
            entries.append((item, {"x": (old_x, item.pos().x()), "y": (old_y, item.pos().y())}))
        self._push(EditPropertiesCommand(self._scene, entries, "微调位置", merge_key="nudge"))

    def rotate_selected(self, delta: float) -> None:
        items = self._selected_items()
        if not items or self._scene is None:
            return
        entries = []
        for item in items:
            old = item.rotation()
            item.setRotation(old + delta)
            entries.append((item, {"rotation": (old, item.rotation())}))
        self._push(EditPropertiesCommand(self._scene, entries, "旋转元素", merge_key="rotate"))

    def flip_selected(self) -> None:
        items = self._selected_items()
        if not items or self._scene is None:
            return
        entries = []
        for item in items:
            if "mirror" not in {field.name for field in item.property_schema()}:
                continue
            old = item.get_prop("mirror")
            item.set_prop("mirror", not old)
            entries.append((item, {"mirror": (old, not old)}))
        if entries:
            self._push(EditPropertiesCommand(self._scene, entries, "翻转元素"))

    # ---------------- 视图 ----------------
    def zoom_in(self) -> None:
        self.view.zoom_in()

    def zoom_out(self) -> None:
        self.view.zoom_out()

    def zoom_reset(self) -> None:
        self.view.reset_zoom()

    def zoom_fit(self) -> None:
        self.view.fit_to_content()
