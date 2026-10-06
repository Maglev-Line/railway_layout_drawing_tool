"""图元基类：统一序列化、属性 schema、端口/手柄协议与选择表现。"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from core import geometry
from ui import theme


@dataclass(frozen=True)
class FieldSpec:
    """属性面板字段描述（界面代码据此生成控件，不写死具体图元）。"""

    name: str
    label: str
    kind: str = "float"  # float / int / str / bool / enum / color / text
    minimum: float = -100000.0
    maximum: float = 100000.0
    step: float = 1.0
    decimals: int = 2
    choices: tuple[tuple[str, str], ...] = ()
    suffix: str = ""
    hint: str = ""


@dataclass(frozen=True)
class Port:
    """场景坐标下的端口：位置 + 离开端口的出射方向（度）。"""

    item: "LayoutItem"
    index: int
    name: str
    pos: QPointF
    angle: float


@dataclass(frozen=True)
class HandleSpec:
    """可拖拽手柄（局部坐标）。"""

    role: str
    pos: QPointF
    cursor: Qt.CursorShape = Qt.CursorShape.CrossCursor


def view_scale(painter) -> float:
    """painter 当前的 场景->屏幕 缩放（用于让装饰保持屏幕尺寸恒定）。"""
    scale = abs(painter.worldTransform().m11())
    return scale if scale > 1e-6 else 1.0


def _resample(points: list[QPointF], step: float = 2.0, max_samples: int = 160) -> list[QPointF]:
    """按弧长重采样折线（沿线做线宽渐变时需要足够密的采样点）。"""
    if len(points) < 2:
        return list(points)
    result = [points[0]]
    total = 0.0
    next_at = step
    for index in range(1, len(points)):
        start, end = points[index - 1], points[index]
        segment = geometry.distance(start, end)
        if segment <= 1e-9:
            continue
        angle = geometry.angle_of(start, end)
        while next_at <= total + segment and len(result) < max_samples:
            result.append(geometry.point_from(start, angle, next_at - total))
            next_at += step
        total += segment
    last = points[-1]
    if len(result) < max_samples and (result[-1].x() != last.x() or result[-1].y() != last.y()):
        result.append(last)
    return result


def tapered_path(path: QPainterPath, start_width: float, end_width: float, taper_length: float) -> QPainterPath:
    """把路径扩成带线宽的填充轮廓，末端 taper_length 内由 start_width 渐变到 end_width。

    QPen 不支持沿线变宽，正线→站线的平滑过渡靠这个轮廓实现。
    """
    outline = QPainterPath()
    for polygon in path.toSubpathPolygons():
        points = _resample(list(polygon))
        if len(points) < 2:
            continue
        lengths = [0.0]
        for index in range(1, len(points)):
            lengths.append(lengths[-1] + geometry.distance(points[index - 1], points[index]))
        total = lengths[-1] if lengths[-1] > 1e-6 else 1.0
        left: list[QPointF] = []
        right: list[QPointF] = []
        for index, point in enumerate(points):
            remaining = total - lengths[index]
            width = start_width
            if taper_length > 0.0 and remaining < taper_length:
                ratio = remaining / taper_length  # 0=端口，1=渐变起点
                width = end_width + (start_width - end_width) * ratio
            half = max(0.2, width) / 2.0
            before = points[index - 1] if index > 0 else points[index]
            after = points[index + 1] if index + 1 < len(points) else points[index]
            angle = geometry.angle_of(before, after) if before != after else 0.0
            normal = geometry.point_from(point, angle + 90.0, half)
            left.append(QPointF(normal.x(), normal.y()))
            offset = geometry.point_from(point, angle - 90.0, half)
            right.append(QPointF(offset.x(), offset.y()))
        outline.moveTo(left[0])
        for point in left[1:]:
            outline.lineTo(point)
        for point in reversed(right):
            outline.lineTo(point)
        outline.closeSubpath()
    return outline


def make_font(size_pt: float, bold: bool = False) -> QFont:
    """统一字体构造（不指定字体族，交给系统默认字体渲染中文）。"""
    font = QFont()
    font.setPointSizeF(float(size_pt))
    font.setBold(bool(bold))
    return font


def draw_center_text(painter, rect: QRectF, text: str, size_pt: float, color: str) -> None:
    if not text:
        return
    painter.setFont(make_font(size_pt))
    painter.setPen(QPen(QColor(color)))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)


class LayoutItem(QGraphicsObject):
    """所有可编辑图元的基类。"""

    TYPE_ID = "item"
    DISPLAY_NAME = "元素"
    DEFAULT_Z = 10.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.uid = uuid4().hex[:8]
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(self.DEFAULT_Z)
        self._hovered = False

    # ---------------- 序列化 ----------------
    def to_dict(self) -> dict:
        data = {
            "type": self.TYPE_ID,
            "id": self.uid,
            "x": round(self.pos().x(), 3),
            "y": round(self.pos().y(), 3),
            "rotation": round(self.rotation(), 3),
            "z": round(self.zValue(), 1),
        }
        data.update(self.extra_dict())
        return data

    def extra_dict(self) -> dict:
        return {}

    def load_dict(self, data: dict) -> None:
        self.uid = str(data.get("id") or self.uid)
        self.setPos(float(data.get("x", 0.0)), float(data.get("y", 0.0)))
        self.setRotation(float(data.get("rotation", 0.0)))
        self.setZValue(float(data.get("z", self.DEFAULT_Z)))
        self.load_extra(data)

    def load_extra(self, data: dict) -> None:
        pass

    @classmethod
    def from_dict(cls, data: dict) -> "LayoutItem":
        item = cls()
        item.load_dict(data)
        return item

    # ---------------- 属性 ----------------
    def property_schema(self) -> list[FieldSpec]:
        return [
            FieldSpec("x", "位置 X", "float", decimals=1, step=5.0),
            FieldSpec("y", "位置 Y", "float", decimals=1, step=5.0),
            FieldSpec("rotation", "旋转角度", "float", -3600.0, 3600.0, 5.0, 1, suffix=" °"),
        ]

    def get_prop(self, name: str):
        if name == "x":
            return self.pos().x()
        if name == "y":
            return self.pos().y()
        if name == "rotation":
            return self.rotation()
        raise KeyError(name)

    def set_prop(self, name: str, value) -> None:
        if name == "x":
            self.setPos(float(value), self.pos().y())
            self.update()
            return
        if name == "y":
            self.setPos(self.pos().x(), float(value))
            self.update()
            return
        if name == "rotation":
            self.setRotation(float(value))
            self.update()
            return
        raise KeyError(name)

    # ---------------- 端口与手柄 ----------------
    def ports(self) -> list[Port]:
        return []

    def handles(self) -> list[HandleSpec]:
        return []

    def begin_handle_drag(self, role: str) -> None:
        pass

    def apply_handle(self, role: str, scene_point: QPointF) -> None:
        pass

    def handle_fields(self, role: str) -> tuple[str, ...]:
        return ()

    # ---------------- 绘制 ----------------
    def paint(self, painter, option, widget=None) -> None:  # noqa: N802 (Qt 命名)
        self.paint_content(painter)
        self.paint_decoration(painter)

    def paint_content(self, painter) -> None:
        raise NotImplementedError

    def paint_decoration(self, painter) -> None:
        selected = self.isSelected()
        if not (selected or self._hovered):
            return
        scale = view_scale(painter)
        color = QColor(theme.ACCENT)
        if not selected:
            color.setAlpha(120)
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 0, Qt.PenStyle.DashLine))
        margin = 4.0 / scale
        painter.drawRect(self.boundingRect().adjusted(-margin, -margin, margin, margin))
        if selected:
            size = 4.0 / scale
            for handle in self.handles():
                painter.setPen(QPen(QColor(theme.ACCENT_TEXT), 0))
                painter.setBrush(QColor(theme.ACCENT))
                painter.drawRect(
                    QRectF(handle.pos.x() - size, handle.pos.y() - size, size * 2, size * 2)
                )
        painter.restore()

    # ---------------- 辅助 ----------------
    def scene_center(self) -> QPointF:
        return self.mapToScene(self.boundingRect().center())

    def is_printable(self) -> bool:
        """是否参与导出（纸张边框、吸附标记等辅助对象返回 False）。"""
        return True

    def itemChange(self, change, value):  # noqa: N802 (Qt 命名)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)


class StrokeItem(LayoutItem):
    """以描边路径呈现的图元（线段、道岔、车挡）。"""

    HIT_WIDTH = 9.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_width = theme.TRACK_WIDTH_DEFAULT
        self.color = theme.TRACK_COLOR
        self.line_style = "实线"

    def build_path(self) -> QPainterPath:
        raise NotImplementedError

    def pen(self) -> QPen:
        pen = QPen(
            QColor(self.color),
            float(self.line_width),
            theme.PEN_STYLES.get(self.line_style, Qt.PenStyle.SolidLine),
        )
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def boundingRect(self) -> QRectF:  # noqa: N802
        rect = self.build_path().boundingRect()
        grow = float(self.line_width) / 2.0 + 10.0
        return rect.adjusted(-grow, -grow, grow, grow)

    def shape(self) -> QPainterPath:  # noqa: N802
        stroker = QPainterPathStroker()
        stroker.setWidth(max(float(self.line_width), self.HIT_WIDTH))
        return stroker.createStroke(self.build_path())

    def paint_content(self, painter) -> None:
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.build_path())

    def property_schema(self) -> list[FieldSpec]:
        return super().property_schema() + [
            FieldSpec("line_width", "线宽", "float", 0.5, 10.0, 0.5, 2),
            FieldSpec("color", "颜色", "color"),
            FieldSpec("line_style", "线型", "enum", choices=tuple((k, k) for k in theme.PEN_STYLES)),
        ]

    def get_prop(self, name: str):
        if name == "line_width":
            return self.line_width
        if name == "color":
            return self.color
        if name == "line_style":
            return self.line_style
        return super().get_prop(name)

    def extra_dict(self) -> dict:
        return {
            "line_width": round(float(self.line_width), 3),
            "color": self.color,
            "line_style": self.line_style,
        }

    def load_extra(self, data: dict) -> None:
        self.line_width = max(0.2, float(data.get("line_width", self.line_width)))
        self.color = str(data.get("color", self.color))
        self.line_style = str(data.get("line_style", self.line_style))

    def set_prop(self, name: str, value) -> None:
        if name == "line_width":
            self.prepareGeometryChange()
            self.line_width = max(0.2, float(value))
            self.update()
            return
        if name == "color":
            self.color = str(value)
            self.update()
            return
        if name == "line_style":
            self.line_style = str(value)
            self.update()
            return
        super().set_prop(name, value)


class RectItem(LayoutItem):
    """以局部矩形呈现的图元：从 (0, -width/2) 到 (length, width/2)（站台、区间标记）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from core import geometry

        self.length = 120.0
        self.width = 16.0
        self.line_width = 1.0
        self.line_color = theme.GRAY_MID
        self.line_style = "实线"
        self.filled = True
        self.fill_color = theme.PLATFORM_FILL
        self._min_length = geometry.MIN_RECT_LENGTH
        self._min_width = geometry.MIN_RECT_WIDTH

    def local_rect(self) -> QRectF:
        return QRectF(0.0, -self.width / 2.0, self.length, self.width)

    def boundingRect(self) -> QRectF:  # noqa: N802
        grow = float(self.line_width) + 16.0
        return self.local_rect().adjusted(-grow, -grow, grow, grow)

    def shape(self) -> QPainterPath:  # noqa: N802
        path = QPainterPath()
        path.addRect(self.local_rect())
        return path

    def pen(self) -> QPen:
        pen = QPen(
            QColor(self.line_color),
            float(self.line_width),
            theme.PEN_STYLES.get(self.line_style, Qt.PenStyle.SolidLine),
        )
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def paint_content(self, painter) -> None:
        painter.setPen(self.pen())
        painter.setBrush(QColor(self.fill_color) if self.filled else Qt.BrushStyle.NoBrush)
        painter.drawRect(self.local_rect())

    def handles(self) -> list[HandleSpec]:
        return [
            HandleSpec("end", QPointF(self.length, 0.0), Qt.CursorShape.SizeHorCursor),
            HandleSpec("width", QPointF(self.length / 2.0, -self.width / 2.0), Qt.CursorShape.SizeVerCursor),
        ]

    def handle_fields(self, role: str) -> tuple[str, ...]:
        if role == "end":
            return ("length",)
        if role == "width":
            return ("width",)
        return ()

    def apply_handle(self, role: str, scene_point: QPointF) -> None:
        local = self.mapFromScene(scene_point)
        if role == "end":
            self.set_prop("length", max(self._min_length, local.x()))
        elif role == "width":
            self.set_prop("width", max(self._min_width, -2.0 * local.y()))

    def property_schema(self) -> list[FieldSpec]:
        return super().property_schema() + [
            FieldSpec("length", "长度", "float", self._min_length, 4000.0, 5.0, 1),
            FieldSpec("width", "宽度", "float", self._min_width, 400.0, 2.0, 1),
            FieldSpec("line_width", "线宽", "float", 0.5, 10.0, 0.5, 2),
            FieldSpec("line_color", "描边色", "color"),
            FieldSpec("line_style", "线型", "enum", choices=tuple((k, k) for k in theme.PEN_STYLES)),
            FieldSpec("filled", "填充", "bool"),
            FieldSpec("fill_color", "填充色", "color"),
        ]

    def get_prop(self, name: str):
        if name == "length":
            return self.length
        if name == "width":
            return self.width
        if name == "line_width":
            return self.line_width
        if name == "line_color":
            return self.line_color
        if name == "line_style":
            return self.line_style
        if name == "filled":
            return self.filled
        if name == "fill_color":
            return self.fill_color
        return super().get_prop(name)

    def set_prop(self, name: str, value) -> None:
        if name in ("length", "width"):
            self.prepareGeometryChange()
            if name == "length":
                self.length = max(self._min_length, float(value))
            else:
                self.width = max(self._min_width, float(value))
            self.update()
            return
        if name == "line_width":
            self.prepareGeometryChange()
            self.line_width = max(0.2, float(value))
            self.update()
            return
        if name == "line_color":
            self.line_color = str(value)
            self.update()
            return
        if name == "line_style":
            self.line_style = str(value)
            self.update()
            return
        if name == "filled":
            self.filled = bool(value)
            self.update()
            return
        if name == "fill_color":
            self.fill_color = str(value)
            self.update()
            return
        super().set_prop(name, value)

    def extra_dict(self) -> dict:
        return {
            "length": round(float(self.length), 3),
            "width": round(float(self.width), 3),
            "line_width": round(float(self.line_width), 3),
            "line_color": self.line_color,
            "line_style": self.line_style,
            "filled": bool(self.filled),
            "fill_color": self.fill_color,
        }

    def load_extra(self, data: dict) -> None:
        self.length = max(self._min_length, float(data.get("length", self.length)))
        self.width = max(self._min_width, float(data.get("width", self.width)))
        self.line_width = max(0.2, float(data.get("line_width", self.line_width)))
        self.line_color = str(data.get("line_color", self.line_color))
        self.line_style = str(data.get("line_style", self.line_style))
        self.filled = bool(data.get("filled", self.filled))
        self.fill_color = str(data.get("fill_color", self.fill_color))
