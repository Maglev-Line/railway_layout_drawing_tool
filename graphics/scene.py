"""配线图画布场景：网格背景、吸附查询、纸张参考框与导出模式。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from core import geometry
from graphics.items.base import LayoutItem, Port
from graphics.items.paper_frame_item import PaperFrameItem
from ui import theme

MAX_GRID_LINES = 4000


@dataclass(frozen=True)
class SnapResult:
    """一次吸附结果：kind 为 port / grid / angle / free。"""

    kind: str
    pos: QPointF
    port: Port | None = None


class SnapMarkerItem(QGraphicsItem):
    """吸附高亮标记：屏幕尺寸恒定的小方框与圆心。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(900.0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.hide()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-9.0, -9.0, 18.0, 18.0)

    def shape(self) -> QPainterPath:  # noqa: N802
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        painter.setPen(QPen(QColor(theme.ACCENT), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(-6.0, -6.0, 12.0, 12.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawEllipse(QPointF(0.0, 0.0), 1.8, 1.8)


class LayoutScene(QGraphicsScene):
    """场景即文档内容：图元持有数据，场景负责绘制与吸附。"""

    itemsChanged = Signal(list)
    textEditRequested = Signal(object)

    CANVAS_RECT = QRectF(-50000.0, -50000.0, 100000.0, 100000.0)

    def __init__(self, document=None, parent=None):
        super().__init__(parent)
        self.document = document
        self.export_mode = False
        self._snap_marker = SnapMarkerItem()
        self.addItem(self._snap_marker)
        self._paper_item = PaperFrameItem()
        self.addItem(self._paper_item)
        self.setSceneRect(self.CANVAS_RECT)
        self.refresh_paper()

    # ---------------- 文档与纸张 ----------------
    def set_document(self, document) -> None:
        self.document = document
        self.refresh_paper()
        self.update()

    def refresh_paper(self) -> None:
        document = self.document
        if document is None:
            self._paper_item.set_paper(0.0, 0.0, "", False)
            return
        width, height = document.paper.size_units()
        self._paper_item.set_paper(width, height, document.paper.describe(), document.paper.show_frame)

    def page_rect(self) -> QRectF:
        if self.document is None:
            return QRectF()
        width, height = self.document.paper.size_units()
        return QRectF(0.0, 0.0, width, height)

    # ---------------- 图元集合 ----------------
    def layout_items(self) -> list[LayoutItem]:
        return [item for item in self.items() if isinstance(item, LayoutItem)]

    def clear_layout(self) -> None:
        for item in self.layout_items():
            self.removeItem(item)

    def bounds(self, printable_only: bool = True) -> QRectF:
        rect = QRectF()
        for item in self.layout_items():
            if not item.isVisible():
                continue
            if printable_only and not item.is_printable():
                continue
            item_rect = item.sceneBoundingRect()
            rect = item_rect if rect.isNull() else rect.united(item_rect)
        return rect

    def content_rect(self) -> QRectF:
        """适配窗口用：有内容用内容，否则用纸张。"""
        rect = self.bounds()
        if rect.isNull():
            rect = self.page_rect()
        return rect

    def printable_rect(self) -> QRectF:
        """导出用：只看图纸内容（纸张参考框不计入）。"""
        rect = self.bounds()
        if rect.isNull():
            rect = self.page_rect()
        return rect

    def notify_items_changed(self, items) -> None:
        self.itemsChanged.emit(list(items))
        self.update()

    # ---------------- 吸附 ----------------
    def nearest_port(self, pos: QPointF, max_dist: float, exclude=()) -> Port | None:
        document = self.document
        if document is not None and not document.snap_ports:
            return None
        excluded = set(exclude)
        best_port: Port | None = None
        best_dist = max_dist
        for item in self.layout_items():
            if item in excluded or not item.isVisible():
                continue
            for port in item.ports():
                dist = geometry.distance(port.pos, pos)
                if dist <= best_dist:
                    best_port, best_dist = port, dist
        return best_port

    def snap_point(self, pos: QPointF, max_dist: float, exclude=(), use_grid: bool = True) -> SnapResult:
        port = self.nearest_port(pos, max_dist, exclude)
        if port is not None:
            return SnapResult("port", QPointF(port.pos), port)
        document = self.document
        if use_grid and document is not None and document.snap_grid:
            return SnapResult("grid", geometry.snap_point_to_grid(pos, document.grid_size))
        return SnapResult("free", QPointF(pos))

    def show_snap(self, snap: SnapResult | None) -> None:
        if snap is None or snap.kind == "free":
            self._snap_marker.hide()
            return
        self._snap_marker.setPos(snap.pos)
        self._snap_marker.show()

    # ---------------- 导出模式 ----------------
    def begin_export(self) -> list:
        saved_selection = list(self.selectedItems())
        self.clearSelection()
        self.export_mode = True
        self._snap_marker.hide()
        self._paper_item.update()
        self.update()
        return saved_selection

    def end_export(self, saved_selection) -> None:
        self.export_mode = False
        for item in saved_selection or []:
            if item.scene() is self:
                item.setSelected(True)
        self._paper_item.update()
        self.update()

    # ---------------- 背景绘制 ----------------
    def drawBackground(self, painter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, QColor(theme.CANVAS_BG))
        document = self.document
        if self.export_mode or document is None or not document.show_grid:
            return
        grid = max(1.0, float(document.grid_size))
        scale = abs(painter.worldTransform().m11()) or 1.0
        step = grid
        while step * scale < 6.0:
            step *= 10.0
        if abs(step - grid) < 1e-9:
            self._draw_grid_lines(painter, rect, step, QColor(theme.GRID_MINOR), scale)
        self._draw_grid_lines(painter, rect, step * 10.0, QColor(theme.GRID_MAJOR), scale)
        painter.setPen(QPen(QColor(theme.PAPER_FRAME), 0))
        painter.drawLine(QPointF(rect.left(), 0.0), QPointF(rect.right(), 0.0))
        painter.drawLine(QPointF(0.0, rect.top()), QPointF(0.0, rect.bottom()))

    def _draw_grid_lines(self, painter, rect: QRectF, step: float, color: QColor, scale: float) -> None:
        if step <= 0 or step * scale < 3.0:
            return
        painter.setPen(QPen(color, 0))
        count = 0
        start_x = math.floor(rect.left() / step) * step
        x = start_x
        while x <= rect.right() and count < MAX_GRID_LINES:
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
            count += 1
        start_y = math.floor(rect.top() / step) * step
        y = start_y
        while y <= rect.bottom() and count < MAX_GRID_LINES:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
            count += 1
