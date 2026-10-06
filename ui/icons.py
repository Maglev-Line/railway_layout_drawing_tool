"""工具图标：用 QPainter 现绘（不引入二进制资源，颜色统一取自 theme）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ui import theme

ICON_SIZE = 22
SCALE = 2  # 2x 绘制，供高 DPI 使用


def _canvas() -> tuple[QPixmap, QPainter]:
    """2x 画布：DPR 已把逻辑坐标缩放到设备像素，切勿再 painter.scale。"""
    pixmap = QPixmap(ICON_SIZE * SCALE, ICON_SIZE * SCALE)
    pixmap.setDevicePixelRatio(SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def _pen(width: float = 1.6, color: str = theme.GRAY_STRONG) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def tool_icon(tool_id: str) -> QIcon:
    pixmap, painter = _canvas()
    brush = QColor(theme.GRAY_STRONG)
    if tool_id == "select":
        path = QPainterPath(QPointF(5.0, 3.0))
        path.lineTo(5.0, 17.0)
        path.lineTo(9.0, 13.2)
        path.lineTo(11.8, 19.0)
        path.lineTo(14.0, 18.0)
        path.lineTo(11.2, 12.4)
        path.lineTo(16.5, 12.0)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(brush)
        painter.drawPath(path)
    elif tool_id == "segment":
        painter.setPen(_pen())
        painter.drawLine(QPointF(4.0, 17.0), QPointF(18.0, 5.0))
        painter.setBrush(brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(4.0, 17.0), 2.0, 2.0)
        painter.drawEllipse(QPointF(18.0, 5.0), 2.0, 2.0)
    elif tool_id in ("turnout", "turnout_single"):
        painter.setPen(_pen())
        painter.drawLine(QPointF(3.0, 16.0), QPointF(19.0, 16.0))
        path = QPainterPath(QPointF(6.0, 16.0))
        path.cubicTo(QPointF(11.0, 16.0), QPointF(13.0, 12.0), QPointF(19.0, 7.0))
        painter.drawPath(path)
    elif tool_id == "platform":
        painter.setPen(_pen())
        painter.setBrush(QColor(theme.PANEL_BG))
        painter.drawRect(QRectF(4.0, 7.0, 14.0, 8.0))
        painter.setPen(_pen(1.0))
        painter.drawLine(QPointF(7.0, 11.0), QPointF(15.0, 11.0))
    elif tool_id == "buffer_stop":
        painter.setPen(_pen(2.4))
        painter.drawLine(QPointF(15.0, 4.0), QPointF(15.0, 18.0))
        painter.setPen(_pen())
        painter.drawLine(QPointF(4.0, 11.0), QPointF(15.0, 11.0))
    elif tool_id == "section_marker":
        pen = _pen()
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(3.0, 7.0, 16.0, 8.0))
    elif tool_id == "text":
        painter.setPen(QPen(QColor(theme.GRAY_STRONG)))
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(11.0)
        painter.setFont(font)
        painter.drawText(QRectF(0.0, 0.0, ICON_SIZE, ICON_SIZE), Qt.AlignmentFlag.AlignCenter, "文")
    elif tool_id == "turnout_symmetric":
        painter.setPen(_pen())
        painter.drawLine(QPointF(3.0, 11.0), QPointF(8.0, 11.0))
        for end in (QPointF(19.0, 4.0), QPointF(19.0, 18.0)):
            path = QPainterPath(QPointF(8.0, 11.0))
            path.cubicTo(QPointF(13.0, 11.0), QPointF(15.0, end.y()), end)
            painter.drawPath(path)
    elif tool_id == "turnout_three":
        painter.setPen(_pen())
        painter.drawLine(QPointF(3.0, 17.0), QPointF(19.0, 17.0))
        for end in (QPointF(19.0, 12.0), QPointF(19.0, 6.0)):
            path = QPainterPath(QPointF(6.0, 17.0))
            path.cubicTo(QPointF(11.0, 17.0), QPointF(14.0, end.y()), end)
            painter.drawPath(path)
    elif tool_id in ("turnout_slip", "turnout_double_slip"):
        painter.setPen(_pen(1.3))
        painter.drawLine(QPointF(3.0, 13.5), QPointF(19.0, 8.5))
        painter.drawLine(QPointF(3.0, 8.5), QPointF(19.0, 13.5))
        # 中间用圆弧过渡成梭形（复式交分两条、单式交分一条）
        upper = QPainterPath(QPointF(6.5, 11.8))
        upper.quadTo(QPointF(11.0, 8.7), QPointF(15.5, 9.2))
        painter.drawPath(upper)
        if tool_id == "turnout_double_slip":
            lower = QPainterPath(QPointF(15.5, 9.2))
            lower.quadTo(QPointF(11.0, 12.3), QPointF(6.5, 11.8))
            painter.drawPath(lower)
    elif tool_id in ("crossover_single", "crossover_double"):
        painter.setPen(_pen(1.5))
        painter.drawLine(QPointF(3.0, 5.5), QPointF(19.0, 5.5))
        painter.drawLine(QPointF(3.0, 16.5), QPointF(19.0, 16.5))
        if tool_id == "crossover_single":
            painter.drawLine(QPointF(8.5, 5.5), QPointF(14.5, 16.5))
        else:
            painter.drawLine(QPointF(6.5, 5.5), QPointF(15.5, 16.5))
            painter.drawLine(QPointF(6.5, 16.5), QPointF(15.5, 5.5))
    elif tool_id == "siding":
        painter.setPen(_pen(1.8))
        painter.drawLine(QPointF(3.0, 17.5), QPointF(19.0, 17.5))
        painter.setPen(_pen(1.4))
        path = QPainterPath(QPointF(6.5, 17.5))
        path.cubicTo(QPointF(11.0, 17.5), QPointF(12.0, 10.5), QPointF(15.0, 10.5))
        painter.drawPath(path)
        painter.drawLine(QPointF(15.0, 10.5), QPointF(18.2, 10.5))
        painter.setPen(_pen(2.2))
        painter.drawLine(QPointF(19.4, 7.0), QPointF(19.4, 14.0))
    elif tool_id == "turnback":
        painter.setPen(_pen(1.1))
        painter.drawLine(QPointF(3.0, 3.5), QPointF(19.0, 3.5))
        painter.drawLine(QPointF(3.0, 18.5), QPointF(19.0, 18.5))
        painter.setPen(_pen(1.5))
        painter.drawLine(QPointF(5.5, 9.0), QPointF(17.0, 9.0))
        painter.drawLine(QPointF(5.5, 13.0), QPointF(17.0, 13.0))
        painter.setPen(_pen(1.1))
        painter.drawLine(QPointF(8.5, 9.0), QPointF(14.0, 13.0))
        painter.drawLine(QPointF(8.5, 13.0), QPointF(14.0, 9.0))
        painter.drawLine(QPointF(5.0, 3.5), QPointF(5.5, 9.0))
        painter.drawLine(QPointF(17.0, 13.0), QPointF(17.5, 18.5))
    painter.end()
    return QIcon(pixmap)


def app_icon() -> QIcon:
    pixmap, painter = _canvas()
    painter.setPen(_pen(1.8))
    painter.drawLine(QPointF(2.0, 15.0), QPointF(20.0, 15.0))
    path = QPainterPath(QPointF(8.0, 15.0))
    path.cubicTo(QPointF(12.0, 15.0), QPointF(14.0, 16.0), QPointF(20.0, 8.0))
    painter.drawPath(path)
    painter.setPen(_pen(1.2))
    painter.setBrush(QColor(theme.PANEL_BG))
    painter.drawRect(QRectF(4.0, 17.0, 12.0, 3.5))
    painter.end()
    return QIcon(pixmap)


def icon_size() -> QSize:
    return QSize(ICON_SIZE, ICON_SIZE)
