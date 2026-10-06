"""配线组合生成测试：渡线 / 存车线 / 折返线的端口贴合与参数范围。"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF

from core import patterns, registry
from graphics.items.base import LayoutItem
from graphics.items.turnout_item import TurnoutItem

TRACK_A = patterns.Track(QPointF(0.0, 0.0), 0.0, 400.0)
TRACK_B = patterns.Track(QPointF(0.0, -60.0), 0.0, 400.0)
SEGMENT_CLS = registry.get("segment").cls
BUFFER_CLS = registry.get("buffer_stop").cls


def _build(kind: str, t: float = 0.0, lean: int = 1, a=TRACK_A, b=TRACK_B) -> list[LayoutItem]:
    return [registry.create_element(data) for data in patterns.build(kind, a, b, t, lean)]


def _of_type(items, cls):
    return [item for item in items if isinstance(item, cls)]


def _ports(item, name: str) -> QPointF:
    return next(port.pos for port in item.ports() if port.name == name)


def _same_point(a: QPointF, b: QPointF) -> bool:
    return abs(a.x() - b.x()) < 1e-6 and abs(a.y() - b.y()) < 1e-6


def test_grip_follows_cursor_side():
    frame = patterns.make_frame(TRACK_A, TRACK_B)
    t, lean = patterns.grip(frame, QPointF(120.0, -10.0))
    assert t == pytest.approx(120.0)
    assert lean == 1  # 靠 A 一侧 → 向前生成
    t, lean = patterns.grip(frame, QPointF(200.0, -50.0))
    assert t == pytest.approx(200.0)
    assert lean == -1  # 越过中线 → 反向生成


def test_frame_rejects_bad_tracks():
    with pytest.raises(patterns.PatternError):
        patterns.make_frame(TRACK_A, patterns.Track(QPointF(0.0, -60.0), 45.0, 400.0))
    with pytest.raises(patterns.PatternError):
        patterns.make_frame(TRACK_A, patterns.Track(QPointF(0.0, -4.0), 0.0, 400.0))


def test_single_crossover_links_two_tracks(qapp):
    items = _build("crossover_single", t=20.0)
    turnouts = _of_type(items, TurnoutItem)
    assert len(turnouts) == 2
    assert len(items) == 2
    # 两道岔分别落在两条股道上，直股沿股道方向
    assert turnouts[0].pos() == QPointF(20.0, 0.0)
    assert turnouts[1].pos() == QPointF(80.0, -60.0)
    assert turnouts[0].rotation() == pytest.approx(0.0)
    assert turnouts[1].rotation() == pytest.approx(180.0)
    # 曲股端口在两条股道正中对接（示例图里的 Z 形斜线）
    frog_a = _ports(turnouts[0], "曲股终端")
    frog_b = _ports(turnouts[1], "曲股终端")
    assert _same_point(frog_a, frog_b)
    assert frog_a == QPointF(50.0, -30.0)
    # 渡线两端是同一手向的道岔，只是朝相反方向
    assert turnouts[0].mirror is turnouts[1].mirror


def test_crossover_is_compact_like_the_sample():
    """45° 斜线：道岔长度 = 间距一半，总跨度 = 间距。"""
    items = patterns.build("crossover_single", TRACK_A, TRACK_B, 0.0, 1)
    assert items[0]["length"] == pytest.approx(30.0)
    assert items[0]["branch_angle"] == pytest.approx(45.0)
    assert items[1]["x"] == pytest.approx(60.0)


def test_double_crossover_crosses_in_the_middle(qapp):
    items = _build("crossover_double", t=0.0)
    turnouts = _of_type(items, TurnoutItem)
    assert len(turnouts) == 4
    # 4 个道岔的曲股端口全部落在正中同一点
    frogs = [_ports(item, "曲股终端") for item in turnouts]
    for frog in frogs[1:]:
        assert frog.x() == pytest.approx(frogs[0].x())
        assert frog.y() == pytest.approx(frogs[0].y())
    assert frogs[0].y() == pytest.approx(-30.0)
    # 每条股道各两个，且互为镜像
    assert sorted(item.pos().y() for item in turnouts) == [-60.0, -60.0, 0.0, 0.0]
    assert sorted(item.mirror for item in turnouts) == [False, False, True, True]


def test_siding_connects_both_ends_to_both_tracks(qapp):
    items = _build("siding", t=0.0)
    segments = _of_type(items, SEGMENT_CLS)
    turnouts = _of_type(items, TurnoutItem)
    assert len(segments) == 1
    assert len(turnouts) == 4
    line = segments[0]
    # 新线夹在两条股道正中，长度取股道一半
    assert line.pos() == QPointF(0.0, -30.0)
    assert line.get_prop("length") == pytest.approx(0.5 * TRACK_A.length)
    start = QPointF(0.0, -30.0)
    end = QPointF(line.get_prop("length"), -30.0)
    frogs = [_ports(item, "曲股终端") for item in turnouts]
    # 上下两条股道各在两端接一个道岔，共 4 个端口两两落在新线端点
    for point in (start, end):
        assert sum(1 for frog in frogs if _same_point(frog, point)) == 2
    assert sorted(item.pos().y() for item in turnouts) == [-60.0, -60.0, 0.0, 0.0]
    assert _of_type(items, BUFFER_CLS) == []  # 两端都接回股道，不需要车挡


def test_turnback_matches_sample_layout(qapp):
    items = _build("turnback", t=0.0)
    turnouts = _of_type(items, TurnoutItem)
    segments = _of_type(items, SEGMENT_CLS)
    stops = _of_type(items, BUFFER_CLS)
    assert len(turnouts) == 8
    assert len(segments) == 2
    assert len(stops) == 2
    # 两条新线夹在两条股道中间
    assert sorted(item.pos().y() for item in segments) == [pytest.approx(-40.0), pytest.approx(-20.0)]
    # 近端略得出头并以车挡收尾（对应示例图左端的挡墙）
    assert all(stop.pos().x() == pytest.approx(-30.0) for stop in stops)
    assert all(stop.rotation() == pytest.approx(180.0) for stop in stops)
    # 每条新线两端各有一个接入道岔（近端在出头 30 处，远端在新线末端）
    frogs = [_ports(item, "曲股终端") for item in turnouts]
    for segment in segments:
        long = segment.get_prop("length")
        y = segment.pos().y()
        for x in (segment.pos().x() + 30.0, segment.pos().x() + long):
            assert sum(1 for frog in frogs if abs(frog.x() - x) < 1e-6 and abs(frog.y() - y) < 1e-6) == 1
    # 交叉渡线的 4 个曲股端口共点（两条新线正中）
    scissors = [frog for frog in frogs if abs(frog.y() + 30.0) < 1e-6]
    assert len(scissors) == 4
    assert max(frog.x() for frog in scissors) - min(frog.x() for frog in scissors) == pytest.approx(0.0, abs=1e-6)
    assert max(frog.y() for frog in scissors) - min(frog.y() for frog in scissors) == pytest.approx(0.0, abs=1e-6)


def test_lean_reverses_generation_direction():
    forward = patterns.build("siding", TRACK_A, TRACK_B, 100.0, 1)
    backward = patterns.build("siding", TRACK_A, TRACK_B, 100.0, -1)
    # 新线始终落在两条股道正中，生成方向决定它向前还是向后延伸
    assert forward[0]["x"] == pytest.approx(100.0)
    assert backward[0]["x"] == pytest.approx(100.0)
    assert forward[0]["rotation"] == pytest.approx(0.0)
    assert backward[0]["rotation"] == pytest.approx(180.0)
    assert forward[0]["y"] == pytest.approx(-30.0)
    assert backward[0]["y"] == pytest.approx(-30.0)
    # 接轨道岔贴在新线两端：道岔原点 = 端点 ± 道岔长度
    assert forward[1]["length"] == pytest.approx(30.0)
    assert sorted(data["x"] for data in forward[1:]) == [
        pytest.approx(70.0),
        pytest.approx(70.0),
        pytest.approx(330.0),
        pytest.approx(330.0),
    ]
    assert sorted(data["x"] for data in backward[1:]) == [
        pytest.approx(-130.0),
        pytest.approx(-130.0),
        pytest.approx(130.0),
        pytest.approx(130.0),
    ]
    assert {data["rotation"] for data in forward[1:]} == {0.0, 180.0}
    assert {data["rotation"] for data in backward[1:]} == {0.0, 180.0}
