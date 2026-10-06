"""右侧属性面板：按图元 schema 或工程设置动态生成表单。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import geometry
from core.commands import EditPropertiesCommand
from core.model import Document
from graphics.items.base import FieldSpec, LayoutItem
from ui import theme
from ui.color_button import ColorButton

ANGLE_STEP_CHOICES = ((0.0, "自由"), (15.0, "15°"), (30.0, "30°"), (45.0, "45°"), (90.0, "90°"))
PAPER_CHOICES = (("A4", "A4"), ("A3", "A3"), ("A2", "A2"), ("custom", "自定义"))
ORIENT_CHOICES = ((True, "横向"), (False, "纵向"))
FOCUS_FIELD_ORDER = ("text", "name", "label", "number")


class PropertyPanel(QWidget):
    """选中元素时编辑其属性；未选中时编辑工程设置。"""

    deleteRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = None
        self._document: Document | None = None
        self._widgets: dict[str, QWidget] = {}
        self._focus_name: str | None = None
        # 合并同一个事件循环内的多次刷新请求，避免一次操作重建表单两遍。
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 9, 6)
        layout.setSpacing(6)

        title = QLabel("属性")
        title.setStyleSheet(theme.CARD_TITLE_QSS)
        layout.addWidget(title)

        self._info = QLabel()
        self._info.setWordWrap(True)
        self._info.setStyleSheet(theme.HINT_QSS)
        layout.addWidget(self._info)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(6)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._scroll.setWidget(self._form_host)
        layout.addWidget(self._scroll, 1)

        self._delete_button = QPushButton("删除选中元素")
        self._delete_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._delete_button.clicked.connect(self.deleteRequested.emit)
        layout.addWidget(self._delete_button)

        footer = QLabel(
            f"单位：1 单位 = {geometry.units_to_mm(1.0):.2f} mm（96dpi 像素）；"
            "勾选元素后可拖动端点手柄改尺寸。"
        )
        footer.setWordWrap(True)
        footer.setStyleSheet(theme.FAINT_QSS)
        layout.addWidget(footer)

    # ---------------- 上下文 ----------------
    def set_context(self, scene, document) -> None:
        if self._scene is not None:
            self._disconnect(self._scene.selectionChanged, self._schedule_refresh)
            self._disconnect(self._scene.itemsChanged, self._on_items_changed)
        if self._document is not None:
            self._disconnect(self._document.settingsChanged, self._schedule_refresh)
        self._scene = scene
        self._document = document
        if scene is not None:
            scene.selectionChanged.connect(self._schedule_refresh)
            scene.itemsChanged.connect(self._on_items_changed)
        if document is not None:
            document.settingsChanged.connect(self._schedule_refresh)
        self.refresh()

    @staticmethod
    def _disconnect(signal, slot) -> None:
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def focus_field(self, name: str = "") -> None:
        """双击元素后聚焦到可编辑字段（内容/名称/编号）。"""
        self._focus_name = name or None
        self.refresh()

    # ---------------- 刷新 ----------------
    def _schedule_refresh(self, *_args) -> None:
        self._refresh_timer.start()

    def _on_items_changed(self, items) -> None:
        self._schedule_refresh()

    def _clear_form(self) -> None:
        # 用 removeRow 连同标签一起删除：takeAt 只摘除控件，会留下空行，
        # 且 setParent(None) 会把控件变成顶层窗口，导致绘制时闪出多个弹窗。
        while self._form.rowCount():
            self._form.removeRow(0)
        self._widgets = {}

    def refresh(self) -> None:
        if self._scene is None:
            return
        self._refresh_timer.stop()
        self._clear_form()
        items = [item for item in self._scene.selectedItems() if isinstance(item, LayoutItem)]
        if items:
            self._build_item_section(items)
        else:
            self._build_document_section()
        if self._focus_name:
            widget = self._widgets.get(self._focus_name)
            self._focus_name = None
            if widget is not None:
                widget.setFocus(Qt.FocusReason.OtherFocusReason)
                if isinstance(widget, QLineEdit):
                    widget.selectAll()

    # ---------------- 元素属性 ----------------
    def _build_item_section(self, items: list[LayoutItem]) -> None:
        first = items[0]
        schemas = [{field.name: field for field in item.property_schema()} for item in items]
        common = [name for name in schemas[0] if all(name in schema for schema in schemas)]
        kinds = {type(item) for item in items}
        if len(items) == 1:
            self._info.setText(f"已选：{first.DISPLAY_NAME}")
        elif len(kinds) == 1:
            self._info.setText(f"已选 {len(items)} 个{first.DISPLAY_NAME}（编辑将同时生效）")
        else:
            self._info.setText(f"已选 {len(items)} 个元素（混合类型），仅显示通用属性")
        for name in common:
            spec = schemas[0][name]
            try:
                value = first.get_prop(name)
            except KeyError:
                continue
            widget = self._make_editor(spec, value, lambda v, n=name, s=spec: self._apply_field(items, n, s, v))
            if widget is None:
                continue
            self._form.addRow(f"{spec.label}：", widget)
            self._widgets[name] = widget

    def _apply_field(self, items: list[LayoutItem], name: str, spec: FieldSpec, value) -> None:
        before = {
            item: {field.name: item.get_prop(field.name) for field in item.property_schema()}
            for item in items
        }
        for item in items:
            try:
                item.set_prop(name, value)
            except (KeyError, TypeError, ValueError):
                continue
        entries = []
        for item in items:
            after = {field.name: item.get_prop(field.name) for field in item.property_schema()}
            props = {
                key: (old, after[key])
                for key, old in before[item].items()
                if key in after and after[key] != old
            }
            if props:
                entries.append((item, props))
        if entries and self._document is not None:
            self._document.undo_stack.push(EditPropertiesCommand(self._scene, entries, f"修改{spec.label}"))
        else:
            self._schedule_refresh()

    # ---------------- 工程设置 ----------------
    def _build_document_section(self) -> None:
        document = self._document
        if document is None:
            return
        self._info.setText("未选中元素：显示工程设置；点击画布中的元素可编辑其属性")

        title_edit = QLineEdit(document.title)
        title_edit.editingFinished.connect(lambda: self._set_document(lambda: setattr(document, "title", title_edit.text())))
        self._add_doc_row("图名", title_edit, "title")

        station_edit = QLineEdit(document.station)
        station_edit.editingFinished.connect(
            lambda: self._set_document(lambda: setattr(document, "station", station_edit.text()))
        )
        self._add_doc_row("站名", station_edit, "station")

        grid_spin = QDoubleSpinBox()
        grid_spin.setRange(1.0, 200.0)
        grid_spin.setSingleStep(1.0)
        grid_spin.setDecimals(1)
        grid_spin.setSuffix(" 单位")
        grid_spin.setValue(document.grid_size)
        grid_spin.valueChanged.connect(lambda v: self._set_document(lambda: setattr(document, "grid_size", float(v)), redraw=True))
        self._add_doc_row("网格间距", grid_spin, "grid_size")

        angle_combo = QComboBox()
        for step, label in ANGLE_STEP_CHOICES:
            angle_combo.addItem(label, step)
        self._select_combo(angle_combo, document.angle_step)
        angle_combo.currentIndexChanged.connect(
            lambda index: self._set_document(lambda: setattr(document, "angle_step", float(angle_combo.itemData(index))))
        )
        self._add_doc_row("角度吸附", angle_combo, "angle_step")

        snap_check = QCheckBox("按网格吸附")
        snap_check.setChecked(document.snap_grid)
        snap_check.toggled.connect(lambda v: self._set_document(lambda: setattr(document, "snap_grid", bool(v))))
        self._add_doc_row("网格吸附", snap_check, "snap_grid")

        show_grid_check = QCheckBox("显示网格")
        show_grid_check.setChecked(document.show_grid)
        show_grid_check.toggled.connect(
            lambda v: self._set_document(lambda: setattr(document, "show_grid", bool(v)), redraw=True)
        )
        self._add_doc_row("显示网格", show_grid_check, "show_grid")

        paper_combo = QComboBox()
        for key, label in PAPER_CHOICES:
            paper_combo.addItem(label, key)
        self._select_combo(paper_combo, document.paper.size_key)
        paper_combo.currentIndexChanged.connect(
            lambda index: self._set_document(lambda: setattr(document.paper, "size_key", str(paper_combo.itemData(index))), paper=True)
        )
        self._add_doc_row("纸张", paper_combo, "paper")

        orient_combo = QComboBox()
        for value, label in ORIENT_CHOICES:
            orient_combo.addItem(label, value)
        orient_combo.setCurrentIndex(0 if document.paper.landscape else 1)
        orient_combo.currentIndexChanged.connect(
            lambda index: self._set_document(lambda: setattr(document.paper, "landscape", bool(orient_combo.itemData(index))), paper=True)
        )
        self._add_doc_row("纸张方向", orient_combo, "orient")

        width_spin = QDoubleSpinBox()
        width_spin.setRange(50.0, 3000.0)
        width_spin.setDecimals(0)
        width_spin.setSuffix(" mm")
        width_spin.setValue(document.paper.custom_width_mm)
        width_spin.valueChanged.connect(
            lambda v: self._set_document(lambda: setattr(document.paper, "custom_width_mm", float(v)), paper=True)
        )
        self._add_doc_row("自定义宽", width_spin, "custom_width")

        height_spin = QDoubleSpinBox()
        height_spin.setRange(50.0, 3000.0)
        height_spin.setDecimals(0)
        height_spin.setSuffix(" mm")
        height_spin.setValue(document.paper.custom_height_mm)
        height_spin.valueChanged.connect(
            lambda v: self._set_document(lambda: setattr(document.paper, "custom_height_mm", float(v)), paper=True)
        )
        self._add_doc_row("自定义高", height_spin, "custom_height")

        frame_check = QCheckBox("显示纸张边框参考线")
        frame_check.setChecked(document.paper.show_frame)
        frame_check.toggled.connect(
            lambda v: self._set_document(lambda: setattr(document.paper, "show_frame", bool(v)), paper=True)
        )
        self._add_doc_row("纸张边框", frame_check, "show_frame")

        autosave_spin = QSpinBox()
        autosave_spin.setRange(15, 600)
        autosave_spin.setSingleStep(15)
        autosave_spin.setSuffix(" 秒")
        autosave_spin.setValue(document.autosave_interval_s)
        autosave_spin.valueChanged.connect(
            lambda v: self._set_document(lambda: setattr(document, "autosave_interval_s", int(v)))
        )
        self._add_doc_row("自动恢复", autosave_spin, "autosave")

    def _add_doc_row(self, label: str, widget: QWidget, key: str) -> None:
        self._form.addRow(f"{label}：", widget)
        self._widgets[key] = widget

    @staticmethod
    def _select_combo(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _set_document(self, mutator, redraw: bool = False, paper: bool = False) -> None:
        document = self._document
        scene = self._scene
        if document is None:
            return
        mutator()
        if paper and scene is not None:
            scene.refresh_paper()
        if redraw and scene is not None:
            scene.update()
        document.notify_settings_changed()

    # ---------------- 控件工厂 ----------------
    def _make_editor(self, spec: FieldSpec, value, on_change):
        if spec.kind == "float":
            spin = QDoubleSpinBox()
            spin.setRange(spec.minimum, spec.maximum)
            spin.setSingleStep(spec.step)
            spin.setDecimals(spec.decimals)
            if spec.suffix:
                spin.setSuffix(spec.suffix)
            spin.setKeyboardTracking(False)
            spin.setValue(float(value))
            spin.valueChanged.connect(lambda v: on_change(float(v)))
            return spin
        if spec.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(spec.minimum), int(spec.maximum))
            spin.setSingleStep(max(1, int(spec.step)))
            spin.setValue(int(value))
            spin.valueChanged.connect(lambda v: on_change(int(v)))
            return spin
        if spec.kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(value))
            check.toggled.connect(lambda v: on_change(bool(v)))
            return check
        if spec.kind == "enum":
            combo = QComboBox()
            current = 0
            for index, (choice_value, label) in enumerate(spec.choices):
                combo.addItem(label, choice_value)
                if str(choice_value) == str(value):
                    current = index
            combo.setCurrentIndex(current)
            combo.currentIndexChanged.connect(lambda index: on_change(combo.itemData(index)))
            return combo
        if spec.kind == "color":
            button = ColorButton(str(value), self, f"选择{spec.label}")
            button.colorChanged.connect(on_change)
            return button
        if spec.kind in ("str", "text"):
            line = QLineEdit(str(value))
            line.editingFinished.connect(lambda: on_change(line.text()))
            return line
        return None
