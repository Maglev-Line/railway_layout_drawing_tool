"""冒烟测试：主窗口装配、绘制命令与撤销栈联动（离屏运行）。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF

from core import autosave, registry
from core.commands import AddItemsCommand, EditPropertiesCommand, RemoveItemsCommand
from core.model import Document
from graphics.scene import LayoutScene
from ui.main_window import MainWindow


def test_main_window_smoke(qapp, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    window = MainWindow()
    document = Document()
    segment = registry.create_default("segment")
    window._add_tab(document, [segment], None)

    assert window.document() is document
    assert window.stack.currentWidget() is window.tabs
    assert window.tabs.count() == 1
    assert window.editor.scene().layout_items() == [segment]
    assert window.windowTitle().endswith("铁路配线图绘制器")
    assert not document.is_dirty()

    document.mark_clean()
    window.close()


def test_scene_snapping_and_commands(qapp):
    document = Document()
    document.grid_size = 10.0
    scene = LayoutScene(document)

    segment = registry.create_default("segment")
    segment.setPos(0.0, 0.0)
    segment.set_prop("length", 100.0)
    scene.addItem(segment)

    ports = segment.ports()
    assert len(ports) == 2
    end = ports[1]
    assert end.pos.x() == 100.0 and end.pos.y() == 0.0
    assert end.angle == 0.0

    snap = scene.snap_point(QPointF(96.0, 3.0), 12.0)
    assert snap.kind == "port"
    assert snap.pos.x() == 100.0

    grid_snap = scene.snap_point(QPointF(64.0, 27.0), 12.0)
    assert grid_snap.kind == "grid"
    assert (grid_snap.pos.x(), grid_snap.pos.y()) == (60.0, 30.0)

    # 添加 -> 撤销 -> 重做
    turnout = registry.create_default("turnout")
    document.undo_stack.push(AddItemsCommand(scene, [turnout], "添加道岔"))
    assert turnout.scene() is scene
    document.undo_stack.undo()
    assert turnout.scene() is None
    document.undo_stack.redo()
    assert turnout.scene() is scene

    # 属性编辑（可合并）与删除
    old_x = segment.pos().x()
    document.undo_stack.push(
        EditPropertiesCommand(scene, [(segment, {"x": (old_x, 40.0)})], "移动元素", merge_key="move")
    )
    assert segment.pos().x() == 40.0
    document.undo_stack.undo()
    assert segment.pos().x() == old_x

    document.undo_stack.push(RemoveItemsCommand(scene, [turnout], "删除元素"))
    assert turnout.scene() is None
    document.undo_stack.undo()
    assert turnout.scene() is scene


def test_snap_disabled_uses_grid(qapp):
    document = Document()
    document.snap_ports = False
    document.grid_size = 10.0
    scene = LayoutScene(document)
    segment = registry.create_default("segment")
    scene.addItem(segment)
    snap = scene.snap_point(QPointF(4.0, 4.0), 12.0)
    assert snap.kind == "grid"
    assert (snap.pos.x(), snap.pos.y()) == (0.0, 0.0)


def test_property_panel_refresh_has_no_popups_and_keeps_rows(qapp, monkeypatch):
    """属性面板重建表单时不应把控件脱离成顶层窗口（会闪出弹窗），也不应累积空行。"""
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    window = MainWindow()
    document = Document()
    segment = registry.create_default("segment")
    segment.set_prop("length", 120.0)
    window._add_tab(document, [segment], None)

    popups: list[str] = []

    class PopupSpy(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            if event.type() in (QEvent.Type.Show, QEvent.Type.WindowActivate):
                try:
                    is_window = obj.isWindow()
                except AttributeError:
                    return False
                if is_window and obj is not window:
                    popups.append(type(obj).__name__)
            return False

    spy = PopupSpy()
    qapp.installEventFilter(spy)
    try:
        panel = window.editor.property_panel
        panel.refresh()
        rows = panel._form.rowCount()
        assert rows > 0
        for _ in range(3):
            panel.refresh()
        assert panel._form.rowCount() == rows
        assert panel._form.count() == rows * 2
    finally:
        qapp.removeEventFilter(spy)

    assert popups == []
    window.close()
