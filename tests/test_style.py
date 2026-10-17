"""默认样式与正线标记测试：设置持久化、线宽联动、组合配线按站线变细。"""
from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath

from core import autosave, patterns, registry
from core.model import Document
from graphics import style as style_module
from graphics.items.base import tapered_path
from graphics.items.segment_item import SegmentItem
from ui.main_window import MainWindow


@pytest.fixture
def restore_style():
    """用例结束后把全局样式还原，避免互相影响。"""
    original = style_module.current()
    yield original
    style_module.save(original)


def test_style_settings_round_trip(restore_style):
    style_module.save(
        style_module.Style(
            distinguish_main=True,
            main=style_module.LineStyle(5.5, "#112233"),
            branch=style_module.LineStyle(2.5, "#445566"),
            taper_length=33.0,
            platform_fill="#ff0000",
            platform_line="#00ff00",
            platform_text="#0000ff",
            platform_fill2="#abcdef",
            break_crossings=True,
        )
    )
    loaded = style_module.reload()
    assert loaded.distinguish_main is True
    assert loaded.main.width == pytest.approx(5.5)
    assert loaded.main.color == "#112233"
    assert loaded.branch.width == pytest.approx(2.5)
    assert loaded.branch.color == "#445566"
    assert loaded.taper_length == pytest.approx(33.0)
    assert loaded.platform_fill == "#ff0000"
    assert loaded.platform_text == "#0000ff"
    assert loaded.platform_fill2 == "#abcdef"
    assert loaded.break_crossings is True


def test_segment_main_flag_applies_style(qapp, restore_style):
    style_module.save(
        replace(
            restore_style,
            distinguish_main=True,
            main=style_module.LineStyle(6.0, "#111111"),
            branch=style_module.LineStyle(2.0, "#222222"),
        )
    )
    segment = SegmentItem()
    assert segment.get_prop("is_main") is True
    segment.set_prop("is_main", False)
    assert segment.get_prop("line_width") == pytest.approx(2.0)
    assert segment.get_prop("color") == "#222222"
    segment.set_prop("is_main", True)
    assert segment.get_prop("line_width") == pytest.approx(6.0)
    assert segment.get_prop("color") == "#111111"


def test_segment_main_flag_is_ignored_when_not_distinguishing(qapp, restore_style):
    style_module.save(replace(restore_style, distinguish_main=False, branch=style_module.LineStyle(1.0, "#333333")))
    segment = SegmentItem()
    width = segment.get_prop("line_width")
    segment.set_prop("is_main", False)
    assert segment.get_prop("line_width") == pytest.approx(width)


def test_pattern_style_makes_branches_thin():
    style = patterns.PatternStyle(branch_width=2.0, new_line_width=2.0, taper_length=40.0)
    items = patterns.build("siding", patterns.Track(QPointF(0.0, 0.0), 0.0, 400.0),
                           patterns.Track(QPointF(0.0, -60.0), 0.0, 400.0), 0.0, 1, style)
    turnouts = [data for data in items if data["type"] == "turnout"]
    lines = [data for data in items if data["type"] == "segment"]
    assert len(turnouts) == 4
    assert all(data["branch_width"] == pytest.approx(2.0) for data in turnouts)
    assert all(data["taper_length"] == pytest.approx(40.0) for data in turnouts)
    assert lines[0]["line_width"] == pytest.approx(2.0)


def test_pattern_without_style_matches_track_width():
    items = patterns.build(
        "crossover_single",
        patterns.Track(QPointF(0.0, 0.0), 0.0, 400.0, width=5.0, color="#123456"),
        patterns.Track(QPointF(0.0, -60.0), 0.0, 400.0, width=5.0, color="#123456"),
        0.0,
        1,
    )
    assert len(items) == 2
    for data in items:
        assert data["line_width"] == pytest.approx(5.0)
        assert data["color"] == "#123456"
        assert "branch_width" not in data  # 不区分正线时不做过渡


def test_pattern_style_keeps_uniform_when_widths_equal():
    style = patterns.PatternStyle(branch_width=4.0, new_line_width=4.0, taper_length=40.0)
    items = patterns.build(
        "crossover_single",
        patterns.Track(QPointF(0.0, 0.0), 0.0, 400.0, width=4.0),
        patterns.Track(QPointF(0.0, -60.0), 0.0, 400.0, width=4.0),
        0.0,
        1,
        style,
    )
    assert all("branch_width" not in data for data in items)


def test_tapered_path_narrows_toward_the_end():
    path = QPainterPath(QPointF(0.0, 0.0))
    path.lineTo(100.0, 0.0)
    ribbon = tapered_path(path, 8.0, 2.0, 20.0)
    assert ribbon.contains(QPointF(10.0, 3.9))  # 起段半宽 4
    assert not ribbon.contains(QPointF(95.0, 3.9))
    assert ribbon.contains(QPointF(95.0, 0.8))  # 末端渐细到半宽 1


def test_restyle_entries_covers_tracks_turnouts_and_stations(qapp, restore_style):
    style = replace(
        restore_style,
        distinguish_main=True,
        main=style_module.LineStyle(6.0, "#101010"),
        branch=style_module.LineStyle(2.0, "#202020"),
        taper_length=25.0,
        platform_fill="#aabbcc",
        platform_line="#ddeeff",
        platform_text="#ffffff",
    )
    main_track = SegmentItem()
    main_track.set_prop("line_width", 9.0)
    main_track.set_prop("color", "#000000")
    side_track = SegmentItem()
    side_track.is_main = False
    side_track.set_prop("line_width", 9.0)
    side_track.set_prop("color", "#000000")
    plain_turnout = registry.create_default("turnout")
    tapered_turnout = registry.create_default("turnout")
    tapered_turnout.set_prop("branch_width", 3.0)
    platform = registry.create_default("platform")
    platform.set_prop("fill_color", "#ffffff")
    platform.set_prop("text_color", "#000000")

    entries = style_module.restyle_entries(
        [main_track, side_track, plain_turnout, tapered_turnout, platform], style
    )
    changed = {id(item): props for item, props in entries}
    assert changed[id(main_track)]["line_width"][1] == pytest.approx(6.0)
    assert changed[id(main_track)]["color"][1] == "#101010"
    assert changed[id(side_track)]["line_width"][1] == pytest.approx(2.0)
    assert changed[id(side_track)]["color"][1] == "#202020"
    # 普通道岔不动；带接轨端线宽的道岔更新过渡参数
    assert id(plain_turnout) not in changed
    assert changed[id(tapered_turnout)]["branch_width"][1] == pytest.approx(2.0)
    assert changed[id(tapered_turnout)]["taper_length"][1] == pytest.approx(25.0)
    assert changed[id(platform)]["fill_color"][1] == "#aabbcc"
    assert changed[id(platform)]["text_color"][1] == "#ffffff"


def test_editor_page_apply_style_is_one_undo_step(qapp, restore_style, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    document = Document()
    window = MainWindow()
    window._add_tab(document, None, None)
    editor = window.editor
    scene = editor.scene()

    track = SegmentItem()
    track.set_prop("length", 200.0)
    track.is_main = False  # 标成站线（不走 set_prop 联动）
    track.set_prop("line_width", 9.0)
    scene.addItem(track)
    platform = registry.create_default("platform")
    scene.addItem(platform)

    style = replace(
        restore_style,
        distinguish_main=True,
        main=style_module.LineStyle(6.0, "#101010"),
        branch=style_module.LineStyle(1.5, "#303030"),
        platform_fill="#123456",
    )
    message = editor.apply_style(style)
    assert "2 个元素" in message
    assert track.get_prop("line_width") == pytest.approx(1.5)
    assert track.get_prop("color") == "#303030"
    assert platform.get_prop("fill_color") == "#123456"
    assert document.undo_stack.count() == 1
    document.undo_stack.undo()
    assert track.get_prop("line_width") == pytest.approx(9.0)
    assert platform.get_prop("fill_color") != "#123456"
    document.undo_stack.redo()
    assert platform.get_prop("fill_color") == "#123456"
    document.mark_clean()  # 关闭前清脏标记，避免弹出保存询问
    window.close()
