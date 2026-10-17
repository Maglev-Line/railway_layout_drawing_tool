"""站台排布：默认间隔（取自 example5）、岛式站台生成、长边吸附与单色/双色/渐变填充。"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QStyleOptionGraphicsItem

from core import patterns, platform, registry
from core.model import Document
from graphics.items.platform_item import PlatformItem
from graphics.items.segment_item import SegmentItem
from graphics.scene import LayoutScene
from graphics.snap_platform import snap_platform
from graphics.tools import ToolManager
from ui.canvas_view import CanvasView

TRACK_A = patterns.Track(QPointF(0.0, 0.0), 0.0, 400.0, width=4.0)
TRACK_B = patterns.Track(QPointF(0.0, -60.0), 0.0, 400.0, width=4.0)


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


def _track(y: float, length: float = 400.0, width: float = 4.0) -> SegmentItem:
    item = SegmentItem()
    item.setPos(0.0, y)
    item.set_prop("length", length)
    item.set_prop("line_width", width)
    return item


def _island(t: float = 0.0, lean: int = 1, a=TRACK_A, b=TRACK_B) -> list[PlatformItem]:
    return [registry.create_element(data) for data in patterns.build("island_platform", a, b, t, lean)]


def _placed(scene, type_id: str) -> list:
    return [
        item for item in scene.layout_items() if item.TYPE_ID == type_id and item.opacity() > 0.9
    ]


# ---------------- 默认间隔 ----------------
def test_default_gap_follows_example5():
    """example5 实测间隔 ≈ 1.4 倍股道线宽；默认线宽 4 → 默认间隔 5.6 单位。"""
    assert platform.PLATFORM_TRACK_GAP_RATIO == pytest.approx(1.4)
    assert platform.gap_for_track(platform.DEFAULT_TRACK_WIDTH) == pytest.approx(
        platform.PLATFORM_TRACK_GAP
    )
    assert platform.gap_for_track(0.0) == pytest.approx(platform.PLATFORM_TRACK_GAP)
    # 很粗的正线：把线宽算进去，至少留出可见间隙
    assert platform.gap_for_track(20.0) == pytest.approx(20.0 / 2.0 + platform.PLATFORM_EDGE_CLEARANCE)


def test_island_metrics_center_between_tracks():
    metrics = platform.island_metrics(60.0, 4.0, 4.0)
    assert metrics.low == pytest.approx(5.6)
    assert metrics.high == pytest.approx(54.4)
    assert metrics.width == pytest.approx(48.8)
    assert metrics.center == pytest.approx(30.0)
    assert platform.fits_island(metrics)
    assert not platform.fits_island(platform.island_metrics(13.0, 4.0, 4.0))


# ---------------- 岛式站台生成 ----------------
def test_island_platform_keeps_gap_on_both_sides(qapp):
    items = _island(t=50.0)
    assert len(items) == 1
    berth = items[0]
    assert berth.get_prop("kind") == "岛式"
    assert berth.get_prop("width") == pytest.approx(48.8)  # 60 − 2 × 默认间隔
    assert berth.get_prop("length") == pytest.approx(200.0)  # 股道长度的一半
    # 站台中线落在两条股道正中，方向与股道一致
    assert berth.pos().y() == pytest.approx(-30.0)
    assert berth.rotation() == pytest.approx(0.0)
    # 两条长边正好各留默认间隔：贴第一条股道一侧 v=5.6、贴第二条股道一侧 v=54.4
    assert berth.mapToScene(QPointF(0.0, 0.0)).y() == pytest.approx(-30.0)
    assert berth.mapToScene(QPointF(0.0, 24.4)).y() == pytest.approx(-5.6)
    assert berth.mapToScene(QPointF(0.0, -24.4)).y() == pytest.approx(-54.4)


def test_island_platform_uses_style_colors(qapp):
    items = [
        registry.create_element(data)
        for data in patterns.build(
            "island_platform",
            TRACK_A,
            TRACK_B,
            0.0,
            1,
            patterns.PatternStyle(
                platform_fill="#111111", platform_fill2="#222222", platform_line="#333333", platform_text="#444444"
            ),
        )
    ]
    berth = items[0]
    assert berth.get_prop("fill_color") == "#111111"
    assert berth.get_prop("fill_color2") == "#222222"
    assert berth.get_prop("line_color") == "#333333"


def test_island_platform_rejects_tight_spacing():
    tight = patterns.Track(QPointF(0.0, -13.0), 0.0, 400.0, width=4.0)
    with pytest.raises(patterns.PatternError):
        _island(b=tight)


# ---------------- 长边吸附 ----------------
def test_snap_edges_math():
    tracks = [platform.TrackOffset(0.0, 4.0), platform.TrackOffset(-60.0, 4.0)]
    # 间距略窄的站台被撑到两条股道的默认间隔上（-54.4 / -5.6）
    a, b, hit_a, hit_b = platform.snap_edges(-50.0, -10.0, tracks, 12.0)
    assert (hit_a, hit_b) == (True, True)
    assert a == pytest.approx(-54.4) and b == pytest.approx(-5.6)
    # 差得太远：不吸附
    a, b, hit_a, hit_b = platform.snap_edges(-50.0, -10.0, tracks, 2.0)
    assert (hit_a, hit_b) == (False, False)
    assert (a, b) == (-50.0, -10.0)
    # 只命中一条长边时，另一条保持不动
    a, b, hit_a, hit_b = platform.snap_edges(-54.5, 25.0, tracks, 12.0)
    assert (hit_a, hit_b) == (True, False)
    assert b == 25.0


def test_platform_edges_snap_to_default_gap(qapp):
    _document, scene, _view, _manager = _make(qapp, grid_size=10.0)
    scene.addItem(_track(0.0))
    scene.addItem(_track(60.0))
    berth = PlatformItem()
    berth.setPos(0.0, 27.0)
    berth.set_prop("length", 100.0)
    berth.set_prop("width", 60.0)
    scene.addItem(berth)

    assert snap_platform(berth, scene, 12.0) is True
    assert berth.get_prop("width") == pytest.approx(48.8)
    assert berth.pos().y() == pytest.approx(30.0)
    assert snap_platform(berth, scene, 12.0) is False  # 已经在位，不再重复吸附


def test_platform_snap_ignores_skewed_and_far_tracks(qapp):
    _document, scene, _view, _manager = _make(qapp, grid_size=10.0)
    skewed = _track(0.0)
    skewed.setRotation(45.0)
    scene.addItem(skewed)
    berth = PlatformItem()
    berth.setPos(0.0, 20.0)
    berth.set_prop("length", 100.0)
    berth.set_prop("width", 30.0)
    scene.addItem(berth)
    assert snap_platform(berth, scene, 12.0) is False

    _document2, scene2, _view2, _manager2 = _make(qapp, grid_size=10.0)
    scene2.addItem(_track(0.0))
    scene2.addItem(_track(60.0))
    far = PlatformItem()
    far.setPos(0.0, 40.0)
    far.set_prop("length", 100.0)
    far.set_prop("width", 36.0)
    scene2.addItem(far)
    assert snap_platform(far, scene2, 2.0) is False


def test_drawing_platform_snaps_between_tracks(qapp):
    """拖出的站台若两条长边都靠近股道，会按默认间隔变成居中的岛式站台。"""
    _document, scene, _view, manager = _make(qapp, grid_size=10.0)
    scene.addItem(_track(0.0))
    scene.addItem(_track(60.0))
    manager.set_tool("platform")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 4.0))
    tool.mouse_release(LEFT, QPointF(120.0, 56.0))

    placed = _placed(scene, "platform")
    assert len(placed) == 1
    berth = placed[0]
    assert berth.get_prop("width") == pytest.approx(48.8)
    assert berth.pos().y() == pytest.approx(30.0)


def test_moving_platform_snaps_and_is_undoable(qapp):
    document, scene, _view, manager = _make(qapp, grid_size=10.0)
    scene.addItem(_track(0.0))
    scene.addItem(_track(60.0))
    berth = PlatformItem()
    berth.setPos(0.0, 26.0)
    berth.set_prop("length", 100.0)
    berth.set_prop("width", 60.0)
    scene.addItem(berth)

    manager.set_tool("select")
    tool = manager.current()
    tool.mouse_press(LEFT, berth.mapToScene(QPointF(50.0, 0.0)))
    tool.mouse_move(LEFT, berth.mapToScene(QPointF(50.0, 1.0)))
    tool.mouse_release(LEFT, berth.mapToScene(QPointF(50.0, 1.0)))
    assert berth.pos().y() == pytest.approx(30.0)
    assert berth.get_prop("width") == pytest.approx(48.8)

    document.undo_stack.undo()
    assert berth.pos().y() == pytest.approx(26.0)
    assert berth.get_prop("width") == pytest.approx(60.0)


# ---------------- 单色 / 双色 / 渐变 ----------------
def test_platform_fill_modes_build_brushes(qapp):
    berth = PlatformItem()
    berth.set_prop("width", 40.0)
    berth.set_prop("length", 200.0)
    assert berth.fill_brush().style() == Qt.BrushStyle.SolidPattern

    berth.set_prop("fill_mode", "渐变")
    assert berth.fill_brush().style() == Qt.BrushStyle.LinearGradientPattern

    berth.set_prop("fill_mode", "双色")
    assert berth.fill_brush().style() == Qt.BrushStyle.SolidPattern
    assert berth._second_half().height() == pytest.approx(20.0)  # 沿宽度对半分
    berth.set_prop("fill_axis", "沿长度")
    assert berth._second_half().width() == pytest.approx(100.0)  # 沿长度对半分
    assert berth._second_half().height() == pytest.approx(40.0)


def _painted(berth: PlatformItem) -> QImage:
    """把站台画到白底图上：局部 (x, y) 落在像素 (20 + x, 40 + y)。"""
    image = QImage(240, 80, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    try:
        painter.translate(20, 40)
        berth.paint(painter, QStyleOptionGraphicsItem())
    finally:
        painter.end()
    return image


@pytest.mark.parametrize(
    ("axis", "first", "second"),
    [("沿宽度", (120, 30), (120, 50)), ("沿长度", (60, 40), (180, 40))],
)
@pytest.mark.parametrize("mode", ["单色", "双色", "渐变"])
def test_platform_paints_every_fill_mode(qapp, mode, axis, first, second):
    """三种填充都要真按主/副色落到画布上（双色曾被补描边时整条刷成副色）。"""
    berth = PlatformItem()
    berth.set_prop("name", "")
    berth.set_prop("length", 200.0)
    berth.set_prop("width", 40.0)
    berth.set_prop("fill_color", "#cc0000")
    berth.set_prop("fill_color2", "#0000cc")
    berth.set_prop("fill_mode", mode)
    berth.set_prop("fill_axis", axis)
    image = _painted(berth)

    head = QColor.fromRgba(image.pixel(*first))
    tail = QColor.fromRgba(image.pixel(*second))
    if mode == "单色":
        assert (head.name(), tail.name()) == ("#cc0000", "#cc0000")
    elif mode == "双色":
        assert head.name() == "#cc0000"
        assert tail.name() == "#0000cc"
    else:
        assert head.name() != tail.name()
        assert head.red() > head.blue()
        assert tail.blue() > tail.red()


def test_platform_fill_fields_round_trip(qapp):
    berth = PlatformItem()
    berth.set_prop("fill_mode", "双色")
    berth.set_prop("fill_color2", "#123456")
    berth.set_prop("fill_axis", "沿长度")
    data = berth.to_dict()
    rebuilt = registry.create_element(data)
    assert rebuilt.get_prop("fill_mode") == "双色"
    assert rebuilt.get_prop("fill_color2") == "#123456"
    assert rebuilt.get_prop("fill_axis") == "沿长度"
    assert rebuilt.to_dict() == data
