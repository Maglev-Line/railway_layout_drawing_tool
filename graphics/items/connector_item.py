"""联络线图元：连接两条交叉股道的斜线（直线 / 曲线两种）。

局部坐标：起点在原点、弦线沿 +X，长度 = 弦长（length）。
- 「直线」型：直接连成一条斜线；
- 「曲线」型：三次贝塞尔，起点切向 = 起点切向角、终点切向 = 终点切向角（均相对弦线，度），
  弯曲程度由 bend（控制点长度 = bend × 弦长）控制——正是 examples/example6 里
  从一条股道顺向过渡到另一条股道的画法。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath

from core import geometry
from graphics.items.base import FieldSpec, HandleSpec, LayoutItem, Port, StrokeItem

KIND_STRAIGHT = "直线"
KIND_CURVE = "曲线"
KINDS = ((KIND_STRAIGHT, KIND_STRAIGHT), (KIND_CURVE, KIND_CURVE))
MIN_LENGTH = geometry.MIN_SEGMENT_LENGTH
DEFAULT_BEND = 0.45  # 与道岔曲股同量级：接近圆弧的顺向过渡
MIN_BEND = 0.05
MAX_BEND = 2.0


class ConnectorItem(StrokeItem):
    TYPE_ID = "connector"
    DISPLAY_NAME = "联络线"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = KIND_CURVE
        self.length = 120.0
        self.bend = DEFAULT_BEND
        self.start_angle = 0.0  # 起点切向（相对弦线，度）
        self.end_angle = 0.0  # 终点切向（相对弦线，度）

    # ---------------- 几何 ----------------
    def is_curve(self) -> bool:
        return self.kind != KIND_STRAIGHT

    def control_points(self) -> tuple[QPointF, QPointF]:
        """贝塞尔控制点：沿两端切向各伸出 bend × 弦长。"""
        start = QPointF(0.0, 0.0)
        end = QPointF(float(self.length), 0.0)
        reach = max(0.0, float(self.bend)) * float(self.length)
        return (
            geometry.point_from(start, float(self.start_angle), reach),
            geometry.point_from(end, float(self.end_angle) + 180.0, reach),
        )

    def build_path(self) -> QPainterPath:
        start = QPointF(0.0, 0.0)
        end = QPointF(float(self.length), 0.0)
        path = QPainterPath(start)
        if not self.is_curve():
            path.lineTo(end)
            return path
        c1, c2 = self.control_points()
        path.cubicTo(c1, c2, end)
        return path

    def mid_point(self) -> QPointF:
        if not self.is_curve():
            return QPointF(float(self.length) / 2.0, 0.0)
        c1, c2 = self.control_points()
        return geometry.cubic_point(QPointF(0.0, 0.0), c1, c2, QPointF(float(self.length), 0.0), 0.5)

    def ports(self) -> list[Port]:
        rotation = self.rotation()
        start = self.mapToScene(QPointF(0.0, 0.0))
        end = self.mapToScene(QPointF(float(self.length), 0.0))
        return [
            Port(self, 0, "起点", start, geometry.normalize_angle(rotation + self.start_angle + 180.0)),
            Port(self, 1, "终端", end, geometry.normalize_angle(rotation + self.end_angle)),
        ]

    # ---------------- 手柄 ----------------
    def handles(self) -> list[HandleSpec]:
        return [
            HandleSpec("start", QPointF(0.0, 0.0), Qt.CursorShape.SizeAllCursor),
            HandleSpec("end", QPointF(float(self.length), 0.0), Qt.CursorShape.CrossCursor),
            HandleSpec("bend", self.mid_point(), Qt.CursorShape.SizeVerCursor),
        ]

    def handle_fields(self, role: str) -> tuple[str, ...]:
        if role == "start":
            return ("x", "y", "rotation", "length")
        if role == "end":
            return ("rotation", "length")
        if role == "bend":
            return ("bend",)
        return ()

    def apply_handle(self, role: str, scene_point: QPointF) -> None:
        if role == "end":
            self.set_prop("rotation", geometry.angle_of(self.pos(), scene_point))
            self.set_prop("length", geometry.distance(self.pos(), scene_point))
        elif role == "start":
            # 拖动起点时终点保持不动（与股道线段一致）
            fixed = self.mapToScene(QPointF(float(self.length), 0.0))
            self.set_prop("x", scene_point.x())
            self.set_prop("y", scene_point.y())
            self.set_prop("rotation", geometry.angle_of(scene_point, fixed))
            self.set_prop("length", geometry.distance(scene_point, fixed))
        elif role == "bend":
            self._stretch_bend(scene_point)

    def _stretch_bend(self, scene_point: QPointF) -> None:
        """拖动中点手柄：让曲线中点跟着光标走，实时改变弯曲程度（越过弦线则反向）。"""
        local = self.mapFromScene(scene_point)
        current = self.mid_point().y()
        if abs(current) <= 1e-6:
            self.set_prop("bend", DEFAULT_BEND if local.y() > 0.0 else -DEFAULT_BEND)
            return
        self.set_prop("bend", float(self.bend) * (local.y() / current))

    # ---------------- 属性 ----------------
    def property_schema(self) -> list[FieldSpec]:
        stroke = [f for f in StrokeItem.property_schema(self) if f.name not in ("x", "y", "rotation")]
        return LayoutItem.property_schema(self) + [
            FieldSpec("kind", "联络线类型", "enum", choices=KINDS),
            FieldSpec("length", "弦长", "float", MIN_LENGTH, 40000.0, 5.0, 1),
            FieldSpec("bend", "弯曲程度", "float", MIN_BEND, MAX_BEND, 0.05, 2, hint="控制点长度 = 该值 × 弦长"),
            FieldSpec("start_angle", "起点切向", "float", -180.0, 180.0, 5.0, 1, suffix=" °"),
            FieldSpec("end_angle", "终点切向", "float", -180.0, 180.0, 5.0, 1, suffix=" °"),
        ] + stroke

    def get_prop(self, name: str):
        if name == "kind":
            return self.kind
        if name == "length":
            return self.length
        if name == "bend":
            return self.bend
        if name == "start_angle":
            return self.start_angle
        if name == "end_angle":
            return self.end_angle
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "kind":
            self.kind = KIND_STRAIGHT if str(value) == KIND_STRAIGHT else KIND_CURVE
            self.prepareGeometryChange()
            self.update()
            return
        if name == "length":
            self.prepareGeometryChange()
            self.length = max(MIN_LENGTH, float(value))
            self.update()
            return
        if name == "bend":
            self.prepareGeometryChange()
            self.bend = max(-MAX_BEND, min(MAX_BEND, float(value)))
            self.update()
            return
        if name in ("start_angle", "end_angle"):
            self.prepareGeometryChange()
            setattr(self, name, float(value))
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
                "bend": round(float(self.bend), 3),
                "start_angle": round(float(self.start_angle), 3),
                "end_angle": round(float(self.end_angle), 3),
            }
        )
        return data

    def load_extra(self, data: dict) -> None:
        super().load_extra(data)
        self.kind = KIND_STRAIGHT if str(data.get("kind")) == KIND_STRAIGHT else KIND_CURVE
        self.length = max(MIN_LENGTH, float(data.get("length", self.length)))
        self.bend = max(-MAX_BEND, min(MAX_BEND, float(data.get("bend", self.bend))))
        self.start_angle = float(data.get("start_angle", self.start_angle))
        self.end_angle = float(data.get("end_angle", self.end_angle))
