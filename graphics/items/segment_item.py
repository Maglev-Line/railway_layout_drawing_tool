"""股道线段图元：以起点为原点、沿局部 +X 方向的中线。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath

from core import geometry
from graphics import style
from graphics.items.base import FieldSpec, HandleSpec, LayoutItem, Port, StrokeItem


class SegmentItem(StrokeItem):
    TYPE_ID = "segment"
    DISPLAY_NAME = "股道线段"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.length = 80.0
        self.is_main = True  # 正线（关闭默认样式里的“区分正线”后仅作标记）
        self.break_at_crossing = False  # 与其它股道交叉时让开空隙（examples/example6 的画法）
        self._drag_fixed_end: QPointF | None = None

    # ---------------- 几何 ----------------
    def build_path(self) -> QPainterPath:
        path = QPainterPath(QPointF(0.0, 0.0))
        path.lineTo(self.length, 0.0)
        return path

    def cross_gaps(self) -> list[tuple[float, float]]:
        """本图元局部 X 轴上的让位区间：交叉点 ± 1.4 × 被跨越股道的线宽。"""
        scene = self.scene()
        if scene is None:
            return []
        start = self.mapToScene(QPointF(0.0, 0.0))
        end = self.mapToScene(QPointF(self.length, 0.0))
        bound = self.sceneBoundingRect().adjusted(-2.0, -2.0, 2.0, 2.0)
        gaps: list[tuple[float, float]] = []
        for other in scene.items(bound, Qt.ItemSelectionMode.IntersectsItemShape):
            if other is self or not isinstance(other, SegmentItem):
                continue
            if other.opacity() < 0.9 or not other.isVisible():  # 预览幽灵不参与
                continue
            hit = geometry.segment_intersection(
                start,
                end,
                other.mapToScene(QPointF(0.0, 0.0)),
                other.mapToScene(QPointF(float(other.length), 0.0)),
            )
            if hit is None:
                continue
            _point, ratio = hit
            half = geometry.CROSS_GAP_FACTOR * max(0.5, float(other.get_prop("line_width")))
            center = ratio * self.length
            gaps.append((center - half, center + half))
        return gaps

    @staticmethod
    def _visible_ranges(length: float, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """把让位区间从 [0, length] 里抠掉，返回要画的若干段。"""
        ranges: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in sorted(gaps):
            if end <= cursor:
                continue
            if start > cursor:
                ranges.append((cursor, min(start, length)))
            cursor = max(cursor, end)
        if cursor < length:
            ranges.append((cursor, length))
        return [(a, b) for a, b in ranges if b - a > 1e-6]

    def render_path(self) -> QPainterPath:
        """绘制用路径（只在勾选「交叉处断开」时分段；数据与命中区域始终是整条线）。"""
        gaps = self.cross_gaps() if self.break_at_crossing else []
        if not gaps:
            return self.build_path()
        path = QPainterPath()
        for start, end in self._visible_ranges(self.length, gaps):
            path.moveTo(start, 0.0)
            path.lineTo(end, 0.0)
        return path

    def paint_content(self, painter) -> None:
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.render_path())

    def ports(self) -> list[Port]:
        start = self.mapToScene(QPointF(0.0, 0.0))
        end = self.mapToScene(QPointF(self.length, 0.0))
        return [
            Port(self, 0, "起点", start, geometry.normalize_angle(self.rotation() + 180.0)),
            Port(self, 1, "终端", end, geometry.normalize_angle(self.rotation())),
        ]

    def handles(self) -> list[HandleSpec]:
        return [
            HandleSpec("start", QPointF(0.0, 0.0), Qt.CursorShape.SizeAllCursor),
            HandleSpec("end", QPointF(self.length, 0.0), Qt.CursorShape.CrossCursor),
        ]

    def handle_fields(self, role: str) -> tuple[str, ...]:
        if role == "start":
            return ("x", "y", "rotation", "length")
        if role == "end":
            return ("rotation", "length")
        return ()

    def begin_handle_drag(self, role: str) -> None:
        if role == "start":
            self._drag_fixed_end = self.mapToScene(QPointF(self.length, 0.0))

    def apply_handle(self, role: str, scene_point: QPointF) -> None:
        if role == "end":
            self.set_prop("rotation", geometry.angle_of(self.pos(), scene_point))
            self.set_prop("length", max(geometry.MIN_SEGMENT_LENGTH, geometry.distance(self.pos(), scene_point)))
        elif role == "start" and self._drag_fixed_end is not None:
            fixed = self._drag_fixed_end
            self.set_prop("x", scene_point.x())
            self.set_prop("y", scene_point.y())
            self.set_prop("rotation", geometry.angle_of(scene_point, fixed))
            self.set_prop("length", max(geometry.MIN_SEGMENT_LENGTH, geometry.distance(scene_point, fixed)))

    # ---------------- 属性 ----------------
    def property_schema(self) -> list[FieldSpec]:
        stroke = [f for f in StrokeItem.property_schema(self) if f.name not in ("x", "y", "rotation")]
        return LayoutItem.property_schema(self) + [
            FieldSpec("is_main", "正线", "bool"),
            FieldSpec("break_at_crossing", "交叉处断开", "bool"),
        ] + stroke + [
            FieldSpec("length", "长度", "float", geometry.MIN_SEGMENT_LENGTH, 40000.0, 5.0, 1),
        ]

    def style_for_main(self) -> None:
        """按「正线」标记套用默认样式（仅在设置里打开“区分正线”时生效）。"""
        current = style.current()
        if not current.distinguish_main:
            return
        line = style.track_style(self.is_main)
        self.set_prop("line_width", line.width)
        self.set_prop("color", line.color)

    def get_prop(self, name: str):
        if name == "is_main":
            return self.is_main
        if name == "break_at_crossing":
            return self.break_at_crossing
        if name == "length":
            return self.length
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name == "is_main":
            self.is_main = bool(value)
            self.style_for_main()
            self.update()
            return
        if name == "break_at_crossing":
            self.break_at_crossing = bool(value)
            self.update()
            return
        if name == "length":
            self.prepareGeometryChange()
            self.length = max(geometry.MIN_SEGMENT_LENGTH, float(value))
            self.update()
            return
        super().set_prop(name, value)

    # ---------------- 序列化 ----------------
    def extra_dict(self) -> dict:
        data = super().extra_dict()
        data["length"] = round(float(self.length), 3)
        data["is_main"] = bool(self.is_main)
        data["break_at_crossing"] = bool(self.break_at_crossing)
        return data

    def load_extra(self, data: dict) -> None:
        super().load_extra(data)
        self.length = max(geometry.MIN_SEGMENT_LENGTH, float(data.get("length", self.length)))
        self.is_main = bool(data.get("is_main", True))
        self.break_at_crossing = bool(data.get("break_at_crossing", False))
