"""绘制指引面板：步骤提示、锚定参照与「其余元素」列表（离屏运行）。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt

from core import registry
from core.model import Document
from ui.editor_page import EditorPage


@dataclass
class StubEvent:
    button_value: Qt.MouseButton = Qt.MouseButton.LeftButton
    modifier_value: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    def button(self):
        return self.button_value

    def modifiers(self):
        return self.modifier_value


LEFT = StubEvent()


def _editor(qapp, items=()):
    editor = EditorPage()
    document = Document()
    document.grid_size = 10.0
    editor.set_document(document, list(items))
    return editor, document


def _track(length: float = 200.0):
    item = registry.create_default("segment")
    item.set_prop("length", length)
    return item


def _rows(guide) -> list[str]:
    return [guide._list.item(index).text() for index in range(guide._list.count())]


def test_step_hint_follows_the_drawing_steps(qapp):
    editor, _document = _editor(qapp)
    guide = editor.guide_panel
    manager = editor.tool_manager

    manager.set_tool("segment")
    assert "第 1 步" in guide._step.text()
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    assert "第 2 步" in guide._step.text()
    tool.cancel()
    assert "第 1 步" in guide._step.text()

    manager.set_tool("turnout_single")
    assert "先点主线" in guide._step.text() or "第 1 步" in guide._step.text()
    manager.current().mouse_press(LEFT, QPointF(400.0, 400.0))
    assert "第 2 步" in guide._step.text()


def test_guide_lists_the_other_elements(qapp):
    editor, _document = _editor(qapp, [_track(), registry.create_default("platform")])
    guide = editor.guide_panel
    texts = _rows(guide)
    assert len(texts) == 2
    assert any("股道线段" in text for text in texts)
    assert any("站台" in text for text in texts)
    assert "2" in guide._list_title.text()


def test_preview_ghosts_are_not_listed(qapp):
    editor, _document = _editor(qapp)
    editor.tool_manager.set_tool("buffer_stop")  # 激活即生成半透明预览幽灵
    editor.tool_manager.current().mouse_move(LEFT, QPointF(20.0, 20.0))
    assert editor.scene().layout_items()  # 场景里确实有预览对象
    assert _rows(editor.guide_panel) == []


def test_anchor_names_the_element_being_aligned_to(qapp):
    track = _track()
    editor, _document = _editor(qapp, [track])
    guide = editor.guide_panel
    editor.tool_manager.set_tool("segment")
    editor.tool_manager.current().mouse_press(LEFT, QPointF(200.0, 0.0))

    assert "当前锚定" in guide._anchor_label.text()
    assert "股道线段" in guide._anchor_label.text()
    assert "终端" in guide._anchor_label.text()
    assert _rows(guide)[0].startswith("◆")

    editor.tool_manager.current().cancel()
    assert "—" in guide._anchor_label.text()
    assert not _rows(guide)[0].startswith("◆")


def test_locating_a_reference_element_selects_it_without_moving_it(qapp):
    track = _track()
    editor, _document = _editor(qapp, [track])
    guide = editor.guide_panel
    guide._list.itemClicked.emit(guide._list.item(0))

    assert track.isSelected()
    assert track.pos() == QPointF(0.0, 0.0)


def test_guide_list_follows_scene_changes(qapp):
    editor, _document = _editor(qapp)
    guide = editor.guide_panel
    scene = editor.scene()
    assert _rows(guide) == []

    item = _track()
    scene.addItem(item)
    scene.notify_items_changed([item])
    assert len(_rows(guide)) == 1

    scene.removeItem(item)
    scene.notify_items_changed([item])
    assert _rows(guide) == []
