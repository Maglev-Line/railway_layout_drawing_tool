"""工具行为测试：拉线、连续绘制、放置对齐、拖画与移动吸附（用桩事件驱动）。"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QPointF, Qt

from core.model import Document
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
RIGHT = StubEvent(button_value=Qt.MouseButton.RightButton)
SHIFT_LEFT = StubEvent(modifier_value=Qt.KeyboardModifier.ShiftModifier)


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


def _items(scene, type_id: str):
    return [item for item in scene.layout_items() if item.TYPE_ID == type_id]


def _placed(scene, type_id: str):
    """已放置的元素（排除半透明预览幽灵）。"""
    return [item for item in _items(scene, type_id) if item.opacity() > 0.9]


def test_segment_drag_snaps_to_grid_and_undoes(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    manager.set_tool("segment")
    tool = manager.current()

    tool.mouse_press(LEFT, QPointF(3.0, 4.0))
    tool.mouse_release(LEFT, QPointF(103.0, 4.0))

    segments = _items(scene, "segment")
    assert len(segments) == 1
    segment = _items(scene, "segment")[0]
    assert segment.pos() == QPointF(0.0, 0.0)
    assert segment.rotation() == pytest.approx(0.0)
    assert segment.get_prop("length") == pytest.approx(100.0)

    document.undo_stack.undo()
    assert _items(scene, "segment") == []
    document.undo_stack.redo()
    assert len(_items(scene, "segment")) == 1


def test_segment_chain_is_one_undo_step(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=0.0)
    manager.set_tool("segment")
    tool = manager.current()

    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    tool.mouse_release(LEFT, QPointF(0.0, 0.0))
    tool.mouse_press(LEFT, QPointF(100.0, 0.0))
    tool.mouse_release(LEFT, QPointF(100.0, 0.0))
    tool.mouse_press(LEFT, QPointF(100.0, 100.0))
    tool.mouse_release(LEFT, QPointF(100.0, 100.0))
    tool.finish_chain()

    segments = _items(scene, "segment")
    assert len(segments) == 2
    second = max(segments, key=lambda item: item.pos().y())
    assert second.rotation() == pytest.approx(90.0)
    assert second.pos() == QPointF(100.0, 0.0)

    document.undo_stack.undo()
    assert _items(scene, "segment") == []


def test_segment_right_click_ends_chain(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    manager.set_tool("segment")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    tool.mouse_release(LEFT, QPointF(0.0, 0.0))
    assert tool.mouse_press(RIGHT, QPointF(10.0, 10.0)) is True
    assert document.undo_stack.count() == 0


def test_turnout_two_step_places_centered_on_track(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    segment = SegmentItem()
    segment.set_prop("length", 100.0)
    scene.addItem(segment)

    manager.set_tool("turnout_single")
    tool = manager.current()

    # 第一步：点主线位置（吸到股道中线上，道岔居中）
    tool.mouse_move(LEFT, QPointF(50.0, 3.0))
    tool.mouse_press(LEFT, QPointF(50.0, 3.0))
    assert _placed(scene, "turnout") == []  # 还没落笔，等支线方向

    # 第二步：拖出曲股方向（光标在股道下方 → 曲股朝下，角度按步长吸附）
    tool.mouse_move(LEFT, QPointF(120.0, 40.0))
    tool.mouse_press(LEFT, QPointF(120.0, 40.0))

    turnouts = _placed(scene, "turnout")
    assert len(turnouts) == 1
    turnout = turnouts[0]
    assert turnout.rotation() == pytest.approx(0.0)
    assert turnout.pos().y() == pytest.approx(0.0)
    assert turnout.pos().x() == pytest.approx(50.0 - turnout.get_prop("length") / 2.0)
    assert turnout.get_prop("branch_angle") == pytest.approx(15.0)
    assert turnout.get_prop("mirror") is False
    # 幽灵仍在，可继续放置
    assert manager.current() is tool


def test_turnout_branch_follows_cursor_side(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    segment = SegmentItem()
    segment.set_prop("length", 100.0)
    scene.addItem(segment)

    manager.set_tool("turnout_single")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(50.0, 0.0))
    # 光标在股道上方、与主线约 -45° → 曲股朝上（single_right 需要翻转），角度吸附到 45°
    tool.mouse_move(LEFT, QPointF(50.0, -60.0))
    tool.mouse_press(LEFT, QPointF(50.0, -60.0))

    turnout = _placed(scene, "turnout")[0]
    assert turnout.get_prop("mirror") is True
    assert turnout.get_prop("branch_angle") == pytest.approx(45.0)


def test_turnout_branch_aligns_to_track_under_cursor(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    main = SegmentItem()
    main.set_prop("length", 200.0)
    scene.addItem(main)
    branch_target = SegmentItem()
    branch_target.set_prop("length", 100.0)
    branch_target.setPos(100.0, 100.0)
    branch_target.setRotation(30.0)
    scene.addItem(branch_target)

    manager.set_tool("turnout_single")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(100.0, 0.0))
    # 第二步光标落在 30° 股道上 → 曲股直接对齐该股道方向
    tool.mouse_move(LEFT, QPointF(117.3, 110.0))
    tool.mouse_press(LEFT, QPointF(117.3, 110.0))

    turnout = _placed(scene, "turnout")[0]
    assert turnout.get_prop("branch_angle") == pytest.approx(30.0)
    assert turnout.get_prop("mirror") is False


def test_turnout_right_click_restarts_step(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    manager.set_tool("turnout_single")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    assert tool.mouse_press(RIGHT, QPointF(0.0, 0.0)) is True
    assert _placed(scene, "turnout") == []
    # 退回第一步后再次点击仍不会落笔，两次左键后才放置
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    assert _placed(scene, "turnout") == []
    tool.mouse_press(LEFT, QPointF(80.0, 0.0))
    assert len(_placed(scene, "turnout")) == 1


def test_place_turnout_aligned_to_segment_end(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    segment = SegmentItem()
    segment.set_prop("length", 100.0)
    scene.addItem(segment)

    manager.set_tool("turnout_single")
    tool = manager.current()
    tool.mouse_move(LEFT, QPointF(101.0, 2.0))
    tool.mouse_press(LEFT, QPointF(101.0, 2.0))
    assert _placed(scene, "turnout") == []
    tool.mouse_move(LEFT, QPointF(160.0, 40.0))
    tool.mouse_press(LEFT, QPointF(160.0, 40.0))

    turnouts = _placed(scene, "turnout")
    assert len(turnouts) == 1
    turnout = turnouts[0]
    assert turnout.pos().x() == pytest.approx(100.0)
    assert turnout.pos().y() == pytest.approx(0.0)
    assert turnout.rotation() == pytest.approx(0.0)
    # 幽灵仍在，可继续放置
    assert manager.current() is tool
    tool.mouse_press(LEFT, QPointF(500.0, 500.0))
    tool.mouse_press(LEFT, QPointF(560.0, 500.0))
    assert len(_placed(scene, "turnout")) == 2


def _two_parallel_tracks(scene, length: float = 400.0, spacing: float = 60.0) -> tuple[SegmentItem, SegmentItem]:
    upper = SegmentItem()
    upper.set_prop("length", length)
    scene.addItem(upper)
    lower = SegmentItem()
    lower.setPos(0.0, spacing)
    lower.set_prop("length", length)
    scene.addItem(lower)
    return upper, lower


def test_pattern_tool_builds_crossover_in_one_undo_step(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    _two_parallel_tracks(scene)

    manager.set_tool("crossover_single")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(100.0, 0.0))
    tool.mouse_press(LEFT, QPointF(100.0, 60.0))
    assert _placed(scene, "turnout") == []  # 两条股道选完先预览，还没落笔
    tool.mouse_move(LEFT, QPointF(120.0, 20.0))
    tool.mouse_press(LEFT, QPointF(120.0, 20.0))

    turnouts = _placed(scene, "turnout")
    assert len(turnouts) == 2
    assert sorted(round(item.pos().x()) for item in turnouts) == [120, 180]
    assert sorted(round(item.pos().y()) for item in turnouts) == [0, 60]
    assert document.undo_stack.count() == 1
    assert all(item.isSelected() for item in turnouts)
    document.undo_stack.undo()
    assert _placed(scene, "turnout") == []


def test_pattern_tool_steps_back_with_right_click(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    upper, lower = _two_parallel_tracks(scene, length=200.0)

    manager.set_tool("siding")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(100.0, 0.0))
    assert upper.isSelected()
    tool.mouse_press(LEFT, QPointF(100.0, 60.0))
    tool.mouse_move(LEFT, QPointF(120.0, 20.0))
    assert tool.mouse_press(RIGHT, QPointF(120.0, 20.0)) is True
    assert not lower.isSelected()
    tool.mouse_press(RIGHT, QPointF(120.0, 20.0))
    assert not upper.isSelected()
    assert len(scene.layout_items()) == 2  # 只有两条股道，没生成任何图元


def test_pattern_tool_rejects_non_parallel_tracks(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    upper = SegmentItem()
    upper.set_prop("length", 200.0)
    scene.addItem(upper)
    skewed = SegmentItem()
    skewed.setPos(0.0, 60.0)
    skewed.setRotation(45.0)
    skewed.set_prop("length", 200.0)
    scene.addItem(skewed)

    messages: list[str] = []
    manager.message.connect(messages.append)
    manager.set_tool("turnback")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(50.0, 0.0))
    tool.mouse_press(LEFT, QPointF(20.0, 80.0))

    assert messages and "方向大致相同" in messages[-1]
    assert len(scene.layout_items()) == 2


def test_pattern_tool_ignores_clicks_off_track(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    _two_parallel_tracks(scene)
    messages: list[str] = []
    manager.message.connect(messages.append)
    manager.set_tool("crossover_double")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(500.0, 500.0))
    assert "请点击股道线段" in messages[-1]


def test_rect_tool_creates_platform(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    manager.set_tool("platform")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    tool.mouse_move(LEFT, QPointF(203.0, 18.0))
    tool.mouse_release(LEFT, QPointF(203.0, 18.0))

    platforms = _placed(scene, "platform")
    assert len(platforms) == 1
    platform = platforms[0]
    assert platform.get_prop("length") == pytest.approx(200.0)
    assert platform.get_prop("width") == pytest.approx(20.0)
    assert platform.pos() == QPointF(0.0, 10.0)


def test_band_tool_creates_marker_with_angle_snap(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0, angle_step=15.0)
    manager.set_tool("section_marker")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    tool.mouse_release(LEFT, QPointF(97.0, 25.0))

    markers = _placed(scene, "section_marker")
    assert len(markers) == 1
    marker = markers[0]
    assert marker.rotation() == pytest.approx(15.0)
    assert marker.get_prop("length") == pytest.approx(100.0)
    assert marker.pos() == QPointF(0.0, 0.0)


def test_select_tool_drag_snaps_to_port_and_undoes(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    movable = SegmentItem()
    scene.addItem(movable)
    target = SegmentItem()
    target.setPos(200.0, 300.0)
    scene.addItem(target)

    manager.set_tool("select")
    tool = manager.current()
    movable.setSelected(True)

    tool.mouse_press(LEFT, QPointF(40.0, 0.0))
    tool.mouse_move(LEFT, QPointF(160.0, 300.0))
    tool.mouse_release(LEFT, QPointF(160.0, 300.0))

    assert movable.pos() == QPointF(120.0, 300.0)
    document.undo_stack.undo()
    assert movable.pos() == QPointF(0.0, 0.0)


def test_select_tool_drag_uses_grid_when_no_port_nearby(qapp):
    document, scene, view, manager = _make(qapp, grid_size=10.0)
    segment = SegmentItem()
    scene.addItem(segment)
    manager.set_tool("select")
    segment.setSelected(True)
    tool = manager.current()

    tool.mouse_press(LEFT, QPointF(40.0, 0.0))
    tool.mouse_move(LEFT, QPointF(73.0, 7.0))
    tool.mouse_release(LEFT, QPointF(73.0, 7.0))

    assert segment.pos() == QPointF(30.0, 10.0)
