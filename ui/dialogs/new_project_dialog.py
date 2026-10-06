"""新建工程对话框：图名、网格与纸张设置。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from core.model import DOC_TITLE_DEFAULT
from core.pdf_export import ORIENT_CHOICES, PAGE_CHOICES
from ui import theme


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建工程")
        self.setModal(True)

        self._title_edit = QLineEdit(DOC_TITLE_DEFAULT, self)

        self._grid_spin = QDoubleSpinBox(self)
        self._grid_spin.setRange(1.0, 200.0)
        self._grid_spin.setDecimals(1)
        self._grid_spin.setSingleStep(1.0)
        self._grid_spin.setValue(10.0)
        self._grid_spin.setSuffix(" 单位")

        self._page_combo = QComboBox(self)
        for key, label in PAGE_CHOICES:
            self._page_combo.addItem(label, key)
        self._page_combo.setCurrentIndex(self._page_combo.findData("A3"))
        self._page_combo.currentIndexChanged.connect(self._update_custom_state)

        self._orient_combo = QComboBox(self)
        for value, label in ORIENT_CHOICES:
            self._orient_combo.addItem(label, value)
        self._orient_combo.setCurrentIndex(self._orient_combo.findData(True))

        self._width_spin = QDoubleSpinBox(self)
        self._width_spin.setRange(50.0, 3000.0)
        self._width_spin.setDecimals(0)
        self._width_spin.setValue(420.0)
        self._width_spin.setSuffix(" mm")

        self._height_spin = QDoubleSpinBox(self)
        self._height_spin.setRange(50.0, 3000.0)
        self._height_spin.setDecimals(0)
        self._height_spin.setValue(297.0)
        self._height_spin.setSuffix(" mm")

        self._frame_check = QCheckBox("显示纸张边框参考线（不导出）", self)
        self._frame_check.setChecked(True)

        form = QFormLayout()
        form.addRow("图名：", self._title_edit)
        form.addRow("网格间距：", self._grid_spin)
        form.addRow("纸张：", self._page_combo)
        form.addRow("方向：", self._orient_combo)
        form.addRow("自定义宽：", self._width_spin)
        form.addRow("自定义高：", self._height_spin)
        form.addRow("纸张边框：", self._frame_check)

        hint = QLabel("纸张尺寸用于画布参考框与 PDF 导出；网格间距决定吸附步长。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)

        ok = theme.ok_button("新建", self)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = theme.cancel_button("取消", self)
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(buttons)

        self._update_custom_state()

    def _update_custom_state(self) -> None:
        custom = self._page_combo.currentData() == "custom"
        self._width_spin.setEnabled(custom)
        self._height_spin.setEnabled(custom)

    # ---------------- 结果 ----------------
    def values(self) -> dict:
        return {
            "title": self._title_edit.text().strip() or DOC_TITLE_DEFAULT,
            "grid_size": float(self._grid_spin.value()),
            "page_key": str(self._page_combo.currentData()),
            "landscape": bool(self._orient_combo.currentData()),
            "custom_width_mm": float(self._width_spin.value()),
            "custom_height_mm": float(self._height_spin.value()),
            "show_frame": bool(self._frame_check.isChecked()),
        }
