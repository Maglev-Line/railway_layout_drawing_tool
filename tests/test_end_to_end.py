"""端到端演练：绘制 → 保存 → 重开 → 导出（对应 README 手测清单）。"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

import pytest
from PySide6.QtCore import QPointF, Qt

from core import autosave, pdf_export, registry, serialize
from core.model import Document
from core.pdf_export import ExportOptions
from ui.main_window import MainWindow


@dataclass
class StubEvent:
    button_value: Qt.MouseButton = Qt.MouseButton.LeftButton
    modifier_value: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier

    def button(self):
        return self.button_value

    def modifiers(self):
        return self.modifier_value


LEFT = StubEvent()


def _placed(scene, type_id: str):
    return [
        item
        for item in scene.layout_items()
        if item.TYPE_ID == type_id and item.opacity() > 0.9
    ]


def test_end_to_end_workflow(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    document = Document()
    document.title = "演练站"
    document.grid_size = 10.0
    window._add_tab(document, None, None)
    editor = window.editor
    editor.view.reset_zoom()  # 固定 100% 缩放，令吸附阈值可预期
    manager = editor.tool_manager
    scene = editor.scene()

    # 1) 拖拽画一条股道，再连续点击画出两条股道
    manager.set_tool("segment")
    tool = manager.current()
    tool.mouse_press(LEFT, QPointF(0.0, 0.0))
    tool.mouse_release(LEFT, QPointF(200.0, 0.0))
    tool.mouse_press(LEFT, QPointF(0.0, 100.0))
    tool.mouse_release(LEFT, QPointF(0.0, 100.0))
    tool.mouse_press(LEFT, QPointF(200.0, 100.0))
    tool.mouse_release(LEFT, QPointF(200.0, 100.0))
    tool.mouse_press(LEFT, QPointF(400.0, 100.0))
    tool.mouse_release(LEFT, QPointF(400.0, 100.0))
    tool.finish_chain()
    assert len(_placed(scene, "segment")) == 3

    # 2) 道岔：先点主线落点，再定曲股方向
    manager.set_tool("turnout_single")
    turnout_tool = manager.current()
    turnout_tool.mouse_move(LEFT, QPointF(201.0, 2.0))
    turnout_tool.mouse_press(LEFT, QPointF(201.0, 2.0))
    turnout_tool.mouse_move(LEFT, QPointF(260.0, 40.0))
    turnout_tool.mouse_press(LEFT, QPointF(260.0, 40.0))
    turnouts = _placed(scene, "turnout")
    assert len(turnouts) == 1
    assert turnouts[0].pos().x() == pytest.approx(200.0)
    assert turnouts[0].pos().y() == pytest.approx(0.0)

    # 3) 站台 / 车挡 / 区间标记 / 文字
    manager.set_tool("platform")
    platform_tool = manager.current()
    platform_tool.mouse_press(LEFT, QPointF(40.0, 6.0))
    platform_tool.mouse_release(LEFT, QPointF(160.0, 24.0))

    manager.set_tool("buffer_stop")
    buffer_tool = manager.current()
    buffer_tool.mouse_move(LEFT, QPointF(399.0, 102.0))
    buffer_tool.mouse_press(LEFT, QPointF(399.0, 102.0))

    manager.set_tool("section_marker")
    marker_tool = manager.current()
    marker_tool.mouse_press(LEFT, QPointF(0.0, 100.0))
    marker_tool.mouse_release(LEFT, QPointF(100.0, 100.0))

    manager.set_tool("text")
    text_tool = manager.current()
    text_tool.mouse_move(LEFT, QPointF(120.0, -60.0))
    text_tool.mouse_press(LEFT, QPointF(120.0, -60.0))

    assert len(_placed(scene, "platform")) == 1
    assert len(_placed(scene, "buffer_stop")) == 1
    assert len(_placed(scene, "section_marker")) == 1
    assert len(_placed(scene, "text")) == 1
    buffers = _placed(scene, "buffer_stop")
    assert buffers[0].pos() == QPointF(400.0, 100.0)
    assert document.is_dirty()

    # 4) 撤销 / 重做
    stack = document.undo_stack
    before = len(scene.layout_items())
    stack.undo()
    stack.undo()
    assert len(scene.layout_items()) == before - 2
    stack.redo()
    stack.redo()
    assert len(scene.layout_items()) == before
    editor.finish_chain()

    # 5) 保存 → 复制一份打开（新标签页）→ 再打开同一文件（切回已有标签页）
    path = tmp_path / "演练站.rld"
    document.file_path = str(path)
    assert window.save_project() is True
    assert path.exists()
    assert not document.is_dirty()

    copy_path = tmp_path / "演练站-副本.rld"
    shutil.copyfile(path, copy_path)
    window.open_project(str(copy_path))
    reopened = window.document()
    assert reopened is not None and reopened is not document
    assert reopened.title == "演练站"
    assert window.tabs.count() == 2
    assert len(_placed(window.editor.scene(), "segment")) == 3
    assert not reopened.is_dirty()

    window.open_project(str(copy_path))
    assert window.tabs.count() == 2  # 同一文件已在标签页中：切回该页，不重复打开
    assert window.document() is reopened

    # 6) 导出 PDF
    pdf_path = tmp_path / "演练站.pdf"
    plan = pdf_export.export_pdf(
        str(pdf_path), window.editor.scene(), reopened, ExportOptions(page_key="A3", landscape=True)
    )
    assert plan.fits
    assert pdf_path.exists() and pdf_path.stat().st_size > 1000

    # 7) 再次保存/关闭时不再提示
    reopened.mark_clean()
    window.close()


def test_autosave_snapshot_and_cleanup(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    window = MainWindow()
    document = Document()
    segment = registry.create_default("segment")
    window._add_tab(document, [segment], None)
    document.mark_dirty()
    window.autosave.save_now()

    entry_path = window.autosave.autosave_path()
    assert entry_path and entry_path.endswith(serialize.FILE_SUFFIX)
    assert os.path.exists(entry_path)

    window.autosave.clear()
    assert not os.path.exists(entry_path)
    document.mark_clean()
    window.close()
