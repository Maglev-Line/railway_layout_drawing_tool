"""画布视图：缩放、平移、工具事件转发与状态信号。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView

from graphics.items.base import LayoutItem

MIN_SCALE = 0.05
MAX_SCALE = 20.0
ZOOM_STEP = 1.15
FIT_MARGIN_PX = 40.0


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)
    cursorMoved = Signal(QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.tool_manager = None
        self._panning = False
        self._pan_point = None
        self._space_held = False

    # ---------------- 缩放 ----------------
    def current_scale(self) -> float:
        scale = abs(self.transform().m11())
        return scale if scale > 1e-9 else 1.0

    def zoom_by(self, factor: float) -> None:
        target = self.current_scale() * factor
        if target < MIN_SCALE or target > MAX_SCALE:
            factor = max(MIN_SCALE, min(MAX_SCALE, target)) / self.current_scale()
        self.scale(factor, factor)
        self.zoomChanged.emit(self.current_scale())

    def zoom_in(self) -> None:
        self.zoom_by(ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom_by(1.0 / ZOOM_STEP)

    def reset_zoom(self) -> None:
        self.resetTransform()
        self.zoomChanged.emit(self.current_scale())

    def fit_to_content(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        rect = scene.content_rect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            self.reset_zoom()
            return
        margin = FIT_MARGIN_PX / max(self.current_scale(), 1e-6)
        target = rect.adjusted(-margin, -margin, margin, margin)
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        scale = self.current_scale()
        if scale > MAX_SCALE:
            self.reset_zoom()
            self.scale(MAX_SCALE, MAX_SCALE)
        elif scale < MIN_SCALE:
            self.reset_zoom()
            self.scale(MIN_SCALE, MIN_SCALE)
        self.zoomChanged.emit(self.current_scale())

    # ---------------- 工具 ----------------
    def set_tool_manager(self, manager) -> None:
        self.tool_manager = manager

    def apply_tool_cursor(self) -> None:
        if self.tool_manager is None:
            return
        tool_id = self.tool_manager.current_id()
        cursor = Qt.CursorShape.ArrowCursor if tool_id == "select" else Qt.CursorShape.CrossCursor
        self.setCursor(cursor)

    # ---------------- 滚轮 ----------------
    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoom_by(ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP)
            event.accept()
            return
        pixel = event.pixelDelta()
        if not pixel.isNull():
            self._scroll_by(pixel.x(), pixel.y())
        else:
            angle = event.angleDelta()
            self._scroll_by(angle.x() / 2.0, angle.y() / 2.0)
        event.accept()

    def _scroll_by(self, dx: float, dy: float) -> None:
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        hbar.setValue(hbar.value() - int(dx))
        vbar.setValue(vbar.value() - int(dy))

    # ---------------- 鼠标 ----------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_held
        ):
            self._panning = True
            self._pan_point = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        pos = self.mapToScene(event.position().toPoint())
        if self.tool_manager is not None and self.tool_manager.dispatch_press(event, pos):
            event.accept()
            return
        if self.tool_manager is not None and self.tool_manager.current_id() == "select":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = self.mapToScene(event.position().toPoint())
        self.cursorMoved.emit(pos)
        if self._panning and self._pan_point is not None:
            current = event.position().toPoint()
            delta = current - self._pan_point
            self._pan_point = current
            self._scroll_by(delta.x(), delta.y())
            event.accept()
            return
        if self.tool_manager is not None and self.tool_manager.dispatch_move(event, pos):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._panning:
            self._panning = False
            self._pan_point = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_held else Qt.CursorShape.ArrowCursor)
            self.apply_tool_cursor()
            event.accept()
            return
        pos = self.mapToScene(event.position().toPoint())
        handled = self.tool_manager is not None and self.tool_manager.dispatch_release(event, pos)
        if not handled:
            super().mouseReleaseEvent(event)
        if self.dragMode() != QGraphicsView.DragMode.NoDrag:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        if handled:
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        pos = self.mapToScene(event.position().toPoint())
        if self.tool_manager is not None and self.tool_manager.dispatch_double(event, pos):
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        while item is not None and not isinstance(item, LayoutItem):
            item = item.parentItem()
        if item is not None and self.scene() is not None:
            self.scene().textEditRequested.emit(item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if scene is not None:
            scene.show_snap(None)
        super().leaveEvent(event)

    # ---------------- 键盘 ----------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.apply_tool_cursor()
            event.accept()
            return
        super().keyReleaseEvent(event)
