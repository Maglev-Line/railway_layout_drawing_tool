"""导出 PDF 对话框：范围、纸张、边距、比例与输出路径。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.pdf_export import (
    ORIENT_CHOICES,
    PAGE_CHOICES,
    SCALE_CHOICES,
    SCOPE_CHOICES,
    ExportOptions,
)
from ui import theme


class ExportPdfDialog(QDialog):
    def __init__(self, default_path: str, page_key: str = "A3", landscape: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出 PDF")
        self.setModal(True)

        self._scope_combo = QComboBox(self)
        for value, label in SCOPE_CHOICES:
            self._scope_combo.addItem(label, value)

        self._page_combo = QComboBox(self)
        for key, label in PAGE_CHOICES:
            self._page_combo.addItem(label, key)
        index = self._page_combo.findData(page_key)
        self._page_combo.setCurrentIndex(index if index >= 0 else self._page_combo.findData("A3"))
        self._page_combo.currentIndexChanged.connect(self._update_custom_state)

        self._orient_combo = QComboBox(self)
        for value, label in ORIENT_CHOICES:
            self._orient_combo.addItem(label, value)
        orient_index = self._orient_combo.findData(bool(landscape))
        self._orient_combo.setCurrentIndex(orient_index if orient_index >= 0 else 0)

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

        self._margin_spin = QDoubleSpinBox(self)
        self._margin_spin.setRange(0.0, 60.0)
        self._margin_spin.setDecimals(1)
        self._margin_spin.setValue(10.0)
        self._margin_spin.setSuffix(" mm")

        self._scale_combo = QComboBox(self)
        for value, label in SCALE_CHOICES:
            self._scale_combo.addItem(label, value)

        self._path_edit = QLineEdit(default_path, self)
        browse = QPushButton("浏览…", self)
        browse.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse)

        form = QFormLayout()
        form.addRow("范围：", self._scope_combo)
        form.addRow("纸张：", self._page_combo)
        form.addRow("方向：", self._orient_combo)
        form.addRow("自定义宽：", self._width_spin)
        form.addRow("自定义高：", self._height_spin)
        form.addRow("页面边距：", self._margin_spin)
        form.addRow("比例：", self._scale_combo)
        form.addRow("输出文件：", path_row)

        hint = QLabel("导出为矢量 PDF：网格、纸张参考线与选中状态不会打印。", self)
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)

        ok = theme.ok_button("导出", self)
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

    def _browse(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "导出 PDF", self._path_edit.text() or "配线图.pdf", "PDF 文件 (*.pdf)"
        )
        if path:
            self._path_edit.setText(path)

    def accept(self) -> None:  # noqa: N802
        path = self._path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "导出 PDF", "请先填写输出文件路径（可点击“浏览…”选择位置）。")
            self._path_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
            self._path_edit.setText(path)
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            QMessageBox.warning(self, "导出 PDF", f"目录不存在：{directory}\n请选择已存在的目录后重试。")
            self._path_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        super().accept()

    # ---------------- 结果 ----------------
    def file_path(self) -> str:
        return self._path_edit.text().strip()

    def options(self) -> ExportOptions:
        return ExportOptions(
            scope=str(self._scope_combo.currentData()),
            page_key=str(self._page_combo.currentData()),
            landscape=bool(self._orient_combo.currentData()),
            custom_width_mm=float(self._width_spin.value()),
            custom_height_mm=float(self._height_spin.value()),
            margin_mm=float(self._margin_spin.value()),
            scale_mode=str(self._scale_combo.currentData()),
        )
