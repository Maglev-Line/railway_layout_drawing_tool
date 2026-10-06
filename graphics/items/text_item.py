"""文字标注图元：站名、注记等自由文字（中心对齐，支持换行）。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainterPath, QPen

from graphics.items.base import FieldSpec, LayoutItem, make_font
from ui import theme


class TextItem(LayoutItem):
    TYPE_ID = "text"
    DISPLAY_NAME = "文字标注"
    DEFAULT_Z = 20.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = "文字"
        self.font_size = theme.TEXT_SIZE_DEFAULT
        self.bold = False
        self.color = theme.LABEL_COLOR

    def font(self):
        return make_font(self.font_size, self.bold)

    def text_rect(self) -> QRectF:
        metrics = QFontMetricsF(self.font())
        rect = metrics.boundingRect(QRectF(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text)
        return QRectF(
            rect.x() - 2.0,
            rect.y() - 2.0,
            max(rect.width(), 8.0) + 4.0,
            max(rect.height(), 8.0) + 4.0,
        )

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self.text_rect()

    def shape(self) -> QPainterPath:  # noqa: N802
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint_content(self, painter) -> None:
        painter.setFont(self.font())
        painter.setPen(QPen(QColor(self.color)))
        painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text)

    def property_schema(self) -> list[FieldSpec]:
        return super().property_schema() + [
            FieldSpec("text", "内容", "str"),
            FieldSpec("font_size", "字号", "float", 5.0, 72.0, 0.5, 1, suffix=" pt"),
            FieldSpec("bold", "加粗", "bool"),
            FieldSpec("color", "颜色", "color"),
        ]

    def get_prop(self, name: str):
        if name == "text":
            return self.text
        if name == "font_size":
            return self.font_size
        if name == "bold":
            return self.bold
        if name == "color":
            return self.color
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "text":
            self.prepareGeometryChange()
            self.text = str(value)
            self.update()
            return
        if name == "font_size":
            self.prepareGeometryChange()
            self.font_size = max(5.0, float(value))
            self.update()
            return
        if name == "bold":
            self.prepareGeometryChange()
            self.bold = bool(value)
            self.update()
            return
        if name == "color":
            self.color = str(value)
            self.update()
            return
        super().set_prop(name, value)

    def extra_dict(self) -> dict:
        return {
            "text": self.text,
            "font_size": round(float(self.font_size), 2),
            "bold": bool(self.bold),
            "color": self.color,
        }

    def load_extra(self, data: dict) -> None:
        self.text = str(data.get("text", self.text))
        self.font_size = max(5.0, float(data.get("font_size", self.font_size)))
        self.bold = bool(data.get("bold", False))
        self.color = str(data.get("color", self.color))
