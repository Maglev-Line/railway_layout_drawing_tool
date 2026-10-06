"""默认样式设置对话框：正线/站线线宽颜色、车站颜色与过渡长度（保存到应用设置）。"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout

from graphics import style as style_module
from ui import theme
from ui.color_button import ColorButton


class StyleDialog(QDialog):
    """改完点「保存」写入 QSettings；也可直接「应用到当前图纸」更新已有元素。"""

    def __init__(self, parent=None, apply_handler=None):
        super().__init__(parent)
        self.setWindowTitle("默认样式设置")
        self.setModal(True)
        self._apply_handler = apply_handler
        current = style_module.current()

        self._distinguish = QCheckBox("区分正线 / 站线（渡线等按站线变细，接轨处平滑过渡）", self)
        self._distinguish.setChecked(current.distinguish_main)

        self._main_width = self._width_spin(current.main.width)
        self._main_color = ColorButton(current.main.color, self, "选择正线颜色")
        self._branch_width = self._width_spin(current.branch.width)
        self._branch_color = ColorButton(current.branch.color, self, "选择站线颜色")

        self._taper = QDoubleSpinBox(self)
        self._taper.setRange(0.0, 300.0)
        self._taper.setSingleStep(5.0)
        self._taper.setDecimals(0)
        self._taper.setSuffix(" 单位")
        self._taper.setValue(float(current.taper_length))

        self._platform_fill = ColorButton(current.platform_fill, self, "选择车站填充色")
        self._platform_line = ColorButton(current.platform_line, self, "选择车站描边色")
        self._platform_text = ColorButton(current.platform_text, self, "选择车站文字色")

        form = QFormLayout()
        form.addRow("", self._distinguish)
        form.addRow("正线线宽：", self._main_width)
        form.addRow("正线颜色：", self._main_color)
        form.addRow("站线线宽：", self._branch_width)
        form.addRow("站线颜色：", self._branch_color)
        form.addRow("过渡长度：", self._taper)
        form.addRow("车站填充色：", self._platform_fill)
        form.addRow("车站描边色：", self._platform_line)
        form.addRow("车站文字色：", self._platform_text)

        hint = QLabel(
            "「保存」只影响之后新建的股道/站台与自动生成的组合配线；"
            "要把当前值套到图纸里已有的元素上，点「应用到当前图纸」（股道按「正线」标记取线型）。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)

        self._feedback = QLabel("", self)
        self._feedback.setWordWrap(True)
        self._feedback.setStyleSheet(theme.HINT_QSS)

        self._apply_button = theme.cancel_button("应用到当前图纸", self)
        self._apply_button.setEnabled(apply_handler is not None)
        self._apply_button.clicked.connect(self._apply_to_drawing)
        reset = theme.cancel_button("恢复默认", self)
        reset.clicked.connect(self._restore_defaults)
        save = theme.ok_button("保存", self)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        cancel = theme.cancel_button("取消", self)
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self._apply_button)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(save)
        buttons.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self._feedback)
        layout.addLayout(buttons)

    def _apply_to_drawing(self) -> None:
        if self._apply_handler is None:
            return
        self._feedback.setText(str(self._apply_handler(self.values()) or ""))

    def _width_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setRange(0.5, 10.0)
        spin.setSingleStep(0.5)
        spin.setDecimals(2)
        spin.setValue(float(value))
        return spin

    def _restore_defaults(self) -> None:
        defaults = style_module.defaults()
        self._distinguish.setChecked(defaults.distinguish_main)
        self._main_width.setValue(defaults.main.width)
        self._main_color.set_color(defaults.main.color)
        self._branch_width.setValue(defaults.branch.width)
        self._branch_color.set_color(defaults.branch.color)
        self._taper.setValue(defaults.taper_length)
        self._platform_fill.set_color(defaults.platform_fill)
        self._platform_line.set_color(defaults.platform_line)
        self._platform_text.set_color(defaults.platform_text)

    def values(self) -> style_module.Style:
        return style_module.Style(
            distinguish_main=bool(self._distinguish.isChecked()),
            main=style_module.LineStyle(float(self._main_width.value()), self._main_color.color()),
            branch=style_module.LineStyle(float(self._branch_width.value()), self._branch_color.color()),
            taper_length=float(self._taper.value()),
            platform_fill=self._platform_fill.color(),
            platform_line=self._platform_line.color(),
            platform_text=self._platform_text.color(),
        )
