"""站台图元：沿局部 +X 轴线的矩形，附站台名称与编号；填充支持单色 / 双色 / 渐变。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient

from graphics.items.base import FieldSpec, LayoutItem, RectItem, draw_center_text
from ui import theme

PLATFORM_KINDS = (("岛式", "岛式"), ("侧式", "侧式"), ("其他", "其他"))
FILL_MODES = (("单色", "单色"), ("双色", "双色"), ("渐变", "渐变"))
FILL_AXES = (("沿宽度", "沿宽度"), ("沿长度", "沿长度"))


class PlatformItem(RectItem):
    TYPE_ID = "platform"
    DISPLAY_NAME = "站台"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.length = 140.0
        self.width = 14.0
        self.fill_color = theme.PLATFORM_FILL
        self.fill_color2 = theme.PLATFORM_FILL2
        self.fill_mode = "单色"
        self.fill_axis = "沿宽度"
        self.line_color = theme.PLATFORM_LINE
        self.text_color = theme.PLATFORM_TEXT
        self.name = "站台"
        self.number = ""
        self.kind = "岛式"
        self.font_size = theme.LABEL_SIZE

    # ---------------- 填充 ----------------
    def _second_half(self) -> QRectF:
        """双色填充的后半段：沿宽度对半分长边，沿长度对半分两端。"""
        rect = self.local_rect()
        if self.fill_axis == "沿长度":
            half = rect.width() / 2.0
            return QRectF(rect.x() + half, rect.y(), half, rect.height())
        half = rect.height() / 2.0
        return QRectF(rect.x(), rect.y() + half, rect.width(), half)

    def fill_brush(self) -> QBrush:
        """按填充方式给出画刷（单色 / 渐变；双色的后半段由 paint_content 另画）。"""
        rect = self.local_rect()
        if self.fill_mode == "渐变":
            if self.fill_axis == "沿长度":
                gradient = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
            else:
                gradient = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
            gradient.setColorAt(0.0, QColor(self.fill_color))
            gradient.setColorAt(1.0, QColor(self.fill_color2))
            return QBrush(gradient)
        return QBrush(QColor(self.fill_color))

    def paint_content(self, painter) -> None:
        rect = self.local_rect()
        pen = self.pen()
        painter.setPen(pen)
        painter.setBrush(self.fill_brush() if self.filled else Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        if self.filled and self.fill_mode == "双色":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.fill_color2))
            painter.drawRect(self._second_half())
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)  # 只补描边，别把副色再铺满整条站台
            painter.drawRect(rect)
        text = "\n".join(part for part in (self.number, self.name) if part)
        color = self.text_color if self.filled else theme.LABEL_COLOR
        draw_center_text(painter, rect, text, self.font_size, color)

    def property_schema(self) -> list[FieldSpec]:
        rect_fields = [
            f
            for f in RectItem.property_schema(self)
            if f.name
            in ("length", "width", "line_width", "line_color", "line_style", "filled", "fill_color")
        ]
        return LayoutItem.property_schema(self) + [
            FieldSpec("name", "名称", "str"),
            FieldSpec("number", "编号", "str"),
            FieldSpec("kind", "站台类型", "enum", choices=PLATFORM_KINDS),
            FieldSpec("font_size", "字号", "float", 5.0, 72.0, 0.5, 1, suffix=" pt"),
            FieldSpec("text_color", "文字色", "color"),
            FieldSpec("fill_mode", "填充方式", "enum", choices=FILL_MODES),
            FieldSpec("fill_color2", "副色", "color"),
            FieldSpec("fill_axis", "分色方向", "enum", choices=FILL_AXES),
        ] + rect_fields

    def get_prop(self, name: str):
        if name == "name":
            return self.name
        if name == "number":
            return self.number
        if name == "kind":
            return self.kind
        if name == "font_size":
            return self.font_size
        if name == "text_color":
            return self.text_color
        if name == "fill_mode":
            return self.fill_mode
        if name == "fill_color2":
            return self.fill_color2
        if name == "fill_axis":
            return self.fill_axis
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "name":
            self.name = str(value)
            self.update()
            return
        if name == "number":
            self.number = str(value)
            self.update()
            return
        if name == "kind":
            self.kind = str(value)
            self.update()
            return
        if name == "font_size":
            self.font_size = max(5.0, float(value))
            self.update()
            return
        if name == "text_color":
            self.text_color = str(value)
            self.update()
            return
        if name == "fill_mode":
            self.fill_mode = str(value)
            self.update()
            return
        if name == "fill_color2":
            self.fill_color2 = str(value)
            self.update()
            return
        if name == "fill_axis":
            self.fill_axis = str(value)
            self.update()
            return
        super().set_prop(name, value)

    def handle_fields(self, role: str) -> tuple[str, ...]:
        if role == "width":
            return ("x", "y", "width")  # 宽度手柄可能触发「默认间隔」吸附，会同时平移基准点
        return super().handle_fields(role)

    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data.update(
            {
                "name": self.name,
                "number": self.number,
                "kind": self.kind,
                "font_size": round(float(self.font_size), 2),
                "text_color": self.text_color,
                "fill_mode": self.fill_mode,
                "fill_color2": self.fill_color2,
                "fill_axis": self.fill_axis,
            }
        )
        return data

    def load_extra(self, data: dict) -> None:
        super().load_extra(data)
        self.name = str(data.get("name", self.name))
        self.number = str(data.get("number", self.number))
        self.kind = str(data.get("kind", self.kind))
        self.font_size = max(5.0, float(data.get("font_size", self.font_size)))
        self.text_color = str(data.get("text_color", theme.PLATFORM_TEXT))
        self.fill_mode = str(data.get("fill_mode", self.fill_mode))
        self.fill_color2 = str(data.get("fill_color2", theme.PLATFORM_FILL2))
        self.fill_axis = str(data.get("fill_axis", self.fill_axis))
