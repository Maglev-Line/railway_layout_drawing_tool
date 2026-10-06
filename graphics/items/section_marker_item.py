"""区间标记图元：桥梁/隧道/路堑/路堤等带状标注（沿局部 +X 轴线）。"""
from __future__ import annotations

from graphics.items.base import FieldSpec, LayoutItem, RectItem, draw_center_text
from ui import theme

STYLE_CHOICES = tuple((name, name) for name in theme.MARKER_PRESETS)


class SectionMarkerItem(RectItem):
    TYPE_ID = "section_marker"
    DISPLAY_NAME = "区间标记"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.length = 180.0
        self.width = 18.0
        self.style = "桥梁"
        self.label = ""
        self.font_size = theme.LABEL_SIZE
        self._apply_preset(self.style)

    def _apply_preset(self, style: str) -> None:
        preset = theme.MARKER_PRESETS.get(style)
        if preset is None:
            return
        fill_color, line_style = preset
        self.filled = fill_color is not None
        if fill_color is not None:
            self.fill_color = fill_color
        self.line_style = line_style

    def paint_content(self, painter) -> None:
        super().paint_content(painter)
        draw_center_text(painter, self.local_rect(), self.label, self.font_size, theme.LABEL_COLOR)

    def property_schema(self) -> list[FieldSpec]:
        rect_fields = [
            f
            for f in RectItem.property_schema(self)
            if f.name
            in ("length", "width", "line_width", "line_color", "line_style", "filled", "fill_color")
        ]
        return LayoutItem.property_schema(self) + [
            FieldSpec("style", "标记样式", "enum", choices=STYLE_CHOICES),
            FieldSpec("label", "注记", "str"),
            FieldSpec("font_size", "字号", "float", 5.0, 72.0, 0.5, 1, suffix=" pt"),
        ] + rect_fields

    def get_prop(self, name: str):
        if name == "style":
            return self.style
        if name == "label":
            return self.label
        if name == "font_size":
            return self.font_size
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "style":
            self.style = str(value)
            self._apply_preset(self.style)
            self.update()
            return
        if name == "label":
            self.label = str(value)
            self.update()
            return
        if name == "font_size":
            self.font_size = max(5.0, float(value))
            self.update()
            return
        super().set_prop(name, value)

    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data.update(
            {
                "style": self.style,
                "label": self.label,
                "font_size": round(float(self.font_size), 2),
            }
        )
        return data

    def load_extra(self, data: dict) -> None:
        self.style = str(data.get("style", self.style))
        self._apply_preset(self.style)
        super().load_extra(data)
        self.label = str(data.get("label", self.label))
        self.font_size = max(5.0, float(data.get("font_size", self.font_size)))
