"""道岔图元：单开/对称/三开/交分，几何来自 core.turnout。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor

from core import turnout
from graphics.items.base import (
    FieldSpec,
    LayoutItem,
    Port,
    StrokeItem,
    draw_center_text,
    tapered_path,
)
from ui import theme


class TurnoutItem(StrokeItem):
    TYPE_ID = "turnout"
    DISPLAY_NAME = "道岔"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "single_right"
        self.length = 120.0
        self.branch_angle = turnout.default_angle(self.kind)
        self.mirror = False
        self.label = ""
        self.branch_width = 0.0  # 曲股（接轨端）线宽，0 = 与直股相同
        self.taper_length = 40.0  # 正线→站线过渡长度
        self._geom = None
        self._geom_key = None

    # ---------------- 几何 ----------------
    def geometry_def(self) -> turnout.TurnoutGeometry:
        key = (
            self.kind,
            round(float(self.length), 3),
            round(float(self.branch_angle), 3),
            bool(self.mirror),
        )
        if self._geom_key != key:
            self._geom = turnout.build_geometry(self.kind, self.length, self.branch_angle, self.mirror)
            self._geom_key = key
        return self._geom

    def build_path(self):
        return self.geometry_def().path

    def local_ports(self):
        return self.geometry_def().ports

    def ports(self) -> list[Port]:
        from core import geometry

        rotation = self.rotation()
        result = []
        for index, local in enumerate(self.local_ports()):
            result.append(
                Port(
                    self,
                    index,
                    local.name,
                    self.mapToScene(local.pos),
                    geometry.normalize_angle(local.angle + rotation),
                )
            )
        return result

    def flip(self) -> None:
        self.set_prop("mirror", not self.mirror)

    # ---------------- 绘制 ----------------
    def paint_content(self, painter) -> None:
        geometry = self.geometry_def()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self.pen())
        painter.drawPath(geometry.main_path)
        branch_width = self.branch_width if self.branch_width > 0.0 else self.line_width
        if geometry.branch_path.isEmpty():
            pass
        elif abs(branch_width - self.line_width) < 1e-6:
            painter.drawPath(geometry.branch_path)
        else:
            # 曲股接轨端渐变到站线线宽（正线→非正线平滑过渡）
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.color))
            painter.drawPath(
                tapered_path(geometry.branch_path, float(self.line_width), branch_width, self.taper_length)
            )
        if not self.label:
            return
        anchor = geometry.label_offset
        draw_center_text(
            painter,
            QRectF(anchor.x() - 30.0, anchor.y() - 10.0, 60.0, 20.0),
            self.label,
            theme.LABEL_SIZE,
            theme.LABEL_COLOR,
        )

    # ---------------- 属性 ----------------
    def property_schema(self) -> list[FieldSpec]:
        stroke = [f for f in StrokeItem.property_schema(self) if f.name not in ("x", "y", "rotation")]
        return LayoutItem.property_schema(self) + [
            FieldSpec("kind", "道岔类型", "enum", choices=turnout.KIND_LABELS),
            FieldSpec("length", "直股长度", "float", turnout.MIN_LENGTH, turnout.MAX_LENGTH, 10.0, 1),
            FieldSpec(
                "branch_angle", "分支角", "float", turnout.MIN_ANGLE, turnout.MAX_ANGLE, 1.0, 1, suffix=" °"
            ),
            FieldSpec("mirror", "翻转（镜像）", "bool"),
            FieldSpec("label", "编号文字", "str"),
            FieldSpec("branch_width", "曲股线宽（0=同直股）", "float", 0.0, 10.0, 0.5, 2),
            FieldSpec("taper_length", "过渡长度", "float", 0.0, 300.0, 5.0, 1),
        ] + stroke

    def get_prop(self, name: str):
        if name == "kind":
            return self.kind
        if name == "length":
            return self.length
        if name == "branch_angle":
            return self.branch_angle
        if name == "mirror":
            return self.mirror
        if name == "label":
            return self.label
        if name == "branch_width":
            return self.branch_width
        if name == "taper_length":
            return self.taper_length
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "kind":
            new_kind = str(value)
            if new_kind not in turnout.KIND_IDS:
                return
            self.prepareGeometryChange()
            old_default = turnout.default_angle(self.kind)
            was_default = abs(self.branch_angle - old_default) < 1e-6
            self.kind = new_kind
            if was_default:
                self.branch_angle = turnout.default_angle(new_kind)
            self._geom_key = None
            self.update()
            return
        if name == "length":
            self.prepareGeometryChange()
            self.length = max(turnout.MIN_LENGTH, min(turnout.MAX_LENGTH, float(value)))
            self._geom_key = None
            self.update()
            return
        if name == "branch_angle":
            self.prepareGeometryChange()
            self.branch_angle = turnout.clamp_angle(self.kind, float(value))
            self._geom_key = None
            self.update()
            return
        if name == "mirror":
            self.prepareGeometryChange()
            self.mirror = bool(value)
            self._geom_key = None
            self.update()
            return
        if name == "label":
            self.label = str(value)
            self.update()
            return
        if name == "branch_width":
            self.branch_width = max(0.0, min(10.0, float(value)))
            self.update()
            return
        if name == "taper_length":
            self.taper_length = max(0.0, float(value))
            self.update()
            return
        super().set_prop(name, value)

    # ---------------- 序列化 ----------------
    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data.update(
            {
                "kind": self.kind,
                "length": round(float(self.length), 3),
                "branch_angle": round(float(self.branch_angle), 3),
                "mirror": bool(self.mirror),
                "label": self.label,
                "branch_width": round(float(self.branch_width), 3),
                "taper_length": round(float(self.taper_length), 3),
            }
        )
        return data

    def load_extra(self, data: dict) -> None:
        super().load_extra(data)
        kind = str(data.get("kind", self.kind))
        self.kind = kind if kind in turnout.KIND_IDS else "single_right"
        self.length = max(turnout.MIN_LENGTH, min(turnout.MAX_LENGTH, float(data.get("length", self.length))))
        self.branch_angle = turnout.clamp_angle(
            self.kind, float(data.get("branch_angle", turnout.default_angle(self.kind)))
        )
        self.mirror = bool(data.get("mirror", False))
        self.label = str(data.get("label", ""))
        self.branch_width = max(0.0, min(10.0, float(data.get("branch_width", 0.0))))
        self.taper_length = max(0.0, float(data.get("taper_length", self.taper_length)))
        self._geom_key = None
