"""站台图元：沿局部 +X 轴线的矩形，附站台名称与编号。"""
from __future__ import annotations

from graphics.items.base import FieldSpec, LayoutItem, RectItem, draw_center_text
from ui import theme

PLATFORM_KINDS = (("岛式", "岛式"), ("侧式", "侧式"), ("其他", "其他"))


class PlatformItem(RectItem):
    TYPE_ID = "platform"
    DISPLAY_NAME = "站台"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.length = 140.0
        self.width = 14.0
        self.fill_color = theme.PLATFORM_FILL
        self.line_color = theme.PLATFORM_LINE
        self.text_color = theme.PLATFORM_TEXT
        self.name = "站台"
        self.number = ""
        self.kind = "岛式"
        self.font_size = theme.LABEL_SIZE

    def paint_content(self, painter) -> None:
        super().paint_content(painter)
        text = "\n".join(part for part in (self.number, self.name) if part)
        color = self.text_color if self.filled else theme.LABEL_COLOR
        draw_center_text(painter, self.local_rect(), text, self.font_size, color)

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
        super().set_prop(name, value)

    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data.update(
            {
                "name": self.name,
                "number": self.number,
                "kind": self.kind,
                "font_size": round(float(self.font_size), 2),
                "text_color": self.text_color,
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
