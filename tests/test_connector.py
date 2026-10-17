"""联络线：两条交叉股道之间的直线/曲线联络线，以及股道在交叉处断开的画法。"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from core import geometry, registry
from core.model import Document
from graphics.items.connector_item import KIND_CURVE, KIND_STRAIGHT, ConnectorItem
from graphics.items.segment_item import SegmentItem
from graphics.scene import LayoutScene
from graphics.tools import ToolManager
from ui.canvas_view import CanvasView


@dataclass
class StubEvent:
    button_value: Qt.MouseButton = Qt.MouseButton.LeftButton
    modifier_value: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    def button(self):
        return self.button_value

    def modifiers(self):
        return self.modifier_value


LEFT = StubEvent()


def _make(qapp, **document_kwargs):
    document = Document()
    for key, value in document_kwargs.items():
        setattr(document, key, value)
    view = CanvasView()
    scene = LayoutScene(document)
    view.setScene(scene)
    manager = ToolManager(view)
    view.set_tool_manager(manager)
    manager.set_context(scene, document)
    return document, scene, view, manager


def _horizontal(y: float = 0.0, length: float = 300.0, width: float = 4.0) -> SegmentItem:
    item = SegmentItem()
    item.setPos(0.0, y)
    item.set_prop("length", length)
    item.set_prop("line_width", width)
    return item


def _vertical(x: float, start_y: float = -100.0, length: float = 300.0, width: float = 4.0) -> SegmentItem:
    item = SegmentItem()
    item.setPos(x, start_y)
    item.setRotation(90.0)
    item.set_prop("length", length)
    item.set_prop("line_width", width)
    return item


def _two_crossing_tracks(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    horizontal = _horizontal()
    vertical = _vertical(100.0)
    scene.addItem(horizontal)
    scene.addItem(vertical)
    return document, scene, manager, horizontal, vertical


def _connectors(scene):
    return [
        item
        for item in scene.layout_items()
        if isinstance(item, ConnectorItem) and item.opacity() > 0.9
    ]


def _same_point(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6


# ---------------- 图元本身 ----------------
def test_ports_continue_the_tangents(qapp):
    line = ConnectorItem()
    line.set_prop("start_angle", 30.0)
    line.set_prop("end_angle", -20.0)
    ports = line.ports()
    assert ports[0].name == "起点"
    assert ports[0].angle == pytest.approx(210.0)  # 起点出射方向 = 切向反向
    assert ports[1].angle == pytest.approx(340.0)  # 终点出射方向 = 终点切向


def test_straight_and_curve_paths_differ(qapp):
    line = ConnectorItem()
    line.set_prop("kind", KIND_STRAIGHT)
    assert line.build_path().elementCount() == 2  # 一条斜线
    line.set_prop("kind", KIND_CURVE)
    line.set_prop("start_angle", 40.0)
    line.set_prop("end_angle", -40.0)
    assert line.build_path().elementCount() == 4  # 三次贝塞尔
    assert abs(line.mid_point().y()) > 1.0  # 曲线明显偏离弦线


def test_bend_handle_scales_and_flips(qapp):
    line = ConnectorItem()
    line.set_prop("start_angle", 40.0)
    line.set_prop("end_angle", -40.0)
    original = float(line.get_prop("bend"))
    mid = line.mid_point()
    line.apply_handle("bend", line.mapToScene(QPointF(mid.x(), mid.y() * 1.5)))
    assert line.get_prop("bend") == pytest.approx(original * 1.5, rel=1e-6)
    line.apply_handle("bend", line.mapToScene(QPointF(mid.x(), -mid.y())))
    assert line.get_prop("bend") < 0.0


def test_connector_round_trip(qapp):
    line = ConnectorItem()
    line.set_prop("kind", KIND_STRAIGHT)
    line.set_prop("length", 180.0)
    line.set_prop("start_angle", 12.5)
    line.set_prop("end_angle", -30.0)
    line.set_prop("bend", 0.8)
    data = line.to_dict()
    rebuilt = registry.create_element(data)
    assert isinstance(rebuilt, ConnectorItem)
    assert rebuilt.to_dict() == data


# ---------------- 工具 ----------------
def test_curve_connector_joins_two_crossing_tracks(qapp):
    document, scene, manager, horizontal, vertical = _two_crossing_tracks(qapp)
    manager.set_tool("connector_curve")
    tool = manager.current()

    assert tool.mouse_press(LEFT, QPointF(150.0, 0.0)) is True  # 第一条股道
    assert tool.mouse_press(LEFT, QPointF(100.0, 50.0)) is True  # 与它交叉的股道
    tool.mouse_move(LEFT, QPointF(60.0, -60.0))
    tool.mouse_press(LEFT, QPointF(60.0, -60.0))

    lines = _connectors(scene)
    assert len(lines) == 1
    line = lines[0]
    assert line.get_prop("kind") == KIND_CURVE
    # 两个接点分别落在两条股道的中线上、且沿股道投影自交叉点量出
    start = line.mapToScene(QPointF(0.0, 0.0))
    end = line.mapToScene(QPointF(float(line.get_prop("length")), 0.0))
    assert _same_point(start, QPointF(60.0, 0.0))
    assert _same_point(end, QPointF(100.0, -60.0))
    # 切向顺着两条股道：起点沿 +x、终点朝上（-y）
    assert line.ports()[0].angle == pytest.approx(180.0)
    assert line.ports()[1].angle == pytest.approx(270.0)
    # 原有股道一点没动
    assert horizontal.pos() == QPointF(0.0, 0.0)
    assert horizontal.get_prop("length") == pytest.approx(300.0)
    assert horizontal.get_prop("break_at_crossing") is False
    assert vertical.pos() == QPointF(100.0, -100.0)
    assert vertical.get_prop("length") == pytest.approx(300.0)
    # 一次撤销就没了，且不影响股道
    assert document.undo_stack.canUndo()
    document.undo_stack.undo()
    assert _connectors(scene) == []
    assert len(scene.layout_items()) == 2


def test_straight_connector_is_a_slanted_line(qapp):
    _document, scene, manager, _horizontal_item, _vertical_item = _two_crossing_tracks(qapp)
    manager.set_tool("connector_straight")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(150.0, 0.0))
    tool.mouse_press(LEFT, QPointF(100.0, 50.0))
    tool.mouse_move(LEFT, QPointF(60.0, -60.0))
    tool.mouse_press(LEFT, QPointF(60.0, -60.0))

    lines = _connectors(scene)
    assert len(lines) == 1
    assert lines[0].get_prop("kind") == KIND_STRAIGHT
    assert lines[0].build_path().elementCount() == 2


def test_connector_requires_crossing_lines(qapp):
    _document, scene, manager, _horizontal_item, _vertical_item = _two_crossing_tracks(qapp)
    parallel = _horizontal(50.0)
    scene.addItem(parallel)
    messages: list[str] = []
    manager.message.connect(messages.append)

    manager.set_tool("connector_curve")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(150.0, 0.0))
    tool.mouse_press(LEFT, QPointF(150.0, 50.0))  # 平行股道：不交叉
    assert _connectors(scene) == []
    assert any("没有交叉" in text for text in messages)


def test_connector_gap_snaps_to_grid(qapp):
    _document, scene, manager, _horizontal_item, _vertical_item = _two_crossing_tracks(qapp)
    manager.set_tool("connector_curve")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(150.0, 0.0))
    tool.mouse_press(LEFT, QPointF(100.0, 50.0))
    tool.mouse_move(LEFT, QPointF(54.0, -64.0))  # 光标先吸网格到 (50, -60)，再沿线投影

    assert _connectors(scene) == []  # 还没点击，只应有预览
    ghost = tool._ghost
    assert ghost is not None
    start = QPointF(50.0, 0.0)
    end = QPointF(100.0, -60.0)
    assert ghost.pos() == start
    assert ghost.get_prop("length") == pytest.approx(geometry.distance(start, end))


# ---------------- 交叉处断开 ----------------
def test_segment_breaks_at_crossing(qapp):
    document, scene, _view, _manager = _make(qapp, grid_size=10.0)
    main = _horizontal(width=4.0)
    crossing = _vertical(100.0, width=6.0)
    scene.addItem(main)
    scene.addItem(crossing)

    assert main.render_path().elementCount() == 2  # 默认整条连续
    main.set_prop("break_at_crossing", True)
    half = geometry.CROSS_GAP_FACTOR * 6.0  # 让位长度按被跨越股道的线宽算
    gaps = main.cross_gaps()
    assert len(gaps) == 1
    assert gaps[0] == pytest.approx((100.0 - half, 100.0 + half))
    assert SegmentItem._visible_ranges(300.0, gaps) == pytest.approx(
        [(0.0, 100.0 - half), (100.0 + half, 300.0)]
    )
    assert main.render_path().elementCount() == 4  # 断开成两段

    image = QImage(360, 80, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        main.paint(painter, QStyleOptionGraphicsItem())
    finally:
        painter.end()
    document.mark_clean()


def test_break_flag_round_trip(qapp):
    segment = SegmentItem()
    segment.set_prop("break_at_crossing", True)
    data = segment.to_dict()
    rebuilt = registry.create_element(data)
    assert rebuilt.get_prop("break_at_crossing") is True
    assert rebuilt.to_dict() == data
