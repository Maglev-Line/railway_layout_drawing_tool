"""纸张边框参考线：仅作绘图参考，不参与导出。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from graphics.items.base import make_font
from ui import theme


class PaperFrameItem(QGraphicsItem):
    """按纸张实际尺寸（mm→场景单位）绘制的虚线参考框，左上角在场景原点。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(-100.0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._width = 0.0
        self._height = 0.0
        self._text = ""
        self.setVisible(False)

    def set_paper(self, width_units: float, height_units: float, text: str, visible: bool) -> None:
        self.prepareGeometryChange()
        self._width = float(width_units)
        self._height = float(height_units)
        self._text = str(text)
        self.setVisible(bool(visible) and self._width > 0 and self._height > 0)
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-4.0, -34.0, self._width + 8.0, self._height + 42.0)

    def shape(self) -> QPainterPath:  # noqa: N802
        path = QPainterPath()
        path.addRect(QRectF(0.0, 0.0, self._width, self._height))
        return path

    def paint(self, painter, option, widget=None) -> None:  # noqa: N802
        if self._width <= 0 or self._height <= 0:
            return
        scene = self.scene()
        if getattr(scene, "export_mode", False):
            return
        painter.setPen(QPen(QColor(theme.PAPER_FRAME), 0, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0.0, 0.0, self._width, self._height))
        painter.setPen(QPen(QColor(theme.GRAY_FAINT)))
        painter.setFont(make_font(8.0))
        painter.drawText(
            QRectF(0.0, -30.0, self._width, 22.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"纸张参考：{self._text}（仅参考，不导出）",
        )
        painter.setPen(QPen(QColor(theme.PAPER_FRAME), 0))
        painter.drawPoint(QPointF(0.0, 0.0))
