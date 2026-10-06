"""车挡图元：垂直于股道的挡车器符号，局部原点为接轨点。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath

from core import geometry
from core.geometry import LocalPort
from graphics.items.base import FieldSpec, LayoutItem, Port, StrokeItem
from ui import theme


class BufferStopItem(StrokeItem):
    TYPE_ID = "buffer_stop"
    DISPLAY_NAME = "车挡"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.width = 24.0
        self.thickness = 6.0

    def build_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(0.0, -self.width / 2.0, self.thickness, self.width))
        path.moveTo(-self.thickness * 1.6, 0.0)
        path.lineTo(0.0, 0.0)
        return path

    def local_ports(self) -> list[LocalPort]:
        return [LocalPort("接轨端", QPointF(0.0, 0.0), 180.0, "stem")]

    def ports(self) -> list[Port]:
        return [
            Port(
                self,
                0,
                "接轨端",
                self.mapToScene(QPointF(0.0, 0.0)),
                geometry.normalize_angle(180.0 + self.rotation()),
            )
        ]

    def paint_content(self, painter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.color))
        painter.drawRect(QRectF(0.0, -self.width / 2.0, self.thickness, self.width))
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(-self.thickness * 1.6, 0.0), QPointF(0.0, 0.0))

    def property_schema(self) -> list[FieldSpec]:
        stroke = [f for f in StrokeItem.property_schema(self) if f.name not in ("x", "y", "rotation")]
        return LayoutItem.property_schema(self) + [
            FieldSpec("width", "挡板宽度", "float", 8.0, 80.0, 2.0, 1),
        ] + stroke

    def get_prop(self, name: str):
        if name == "width":
            return self.width
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "width":
            self.prepareGeometryChange()
            self.width = max(8.0, float(value))
            self.update()
            return
        super().set_prop(name, value)

    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data["width"] = round(float(self.width), 3)
        return data

    def load_extra(self, data: dict) -> None:
        super().load_extra(data)
        self.width = max(8.0, float(data.get("width", self.width)))
