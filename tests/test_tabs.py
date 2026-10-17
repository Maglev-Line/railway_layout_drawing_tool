"""多工程标签页：新建/打开各占一页、关闭与标题联动、自动恢复各自独立（离屏运行）。"""
from __future__ import annotations

import os

import pytest

from core import autosave, registry, serialize
from core.model import Document
from graphics.scene import LayoutScene
from ui import theme
from ui.main_window import CREDIT_TEXT, MainWindow


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.setattr(autosave, "pending_recovery", lambda: None)
    win = MainWindow()
    yield win
    for index in range(win.tabs.count()):
        editor = win.tabs.widget(index)
        document = editor.document()
        if document is not None:
            document.mark_clean()
    win.close()


def _write_project(tmp_path, title: str, element_count: int = 1) -> str:
    """直接写一份 .rld 到临时目录，供「打开工程」使用。"""
    document = Document()
    document.title = title
    scene = LayoutScene(document)
    for _ in range(element_count):
        scene.addItem(registry.create_default("segment"))
    path = tmp_path / f"{title}.rld"
    serialize.save_project(str(path), document, scene)
    return str(path)


def test_credit_text_stays_in_status_bar(window):
    assert window._credit_label.text() == CREDIT_TEXT
    assert theme.GRAY_FAINT in window._credit_label.styleSheet()


def test_welcome_page_until_first_project(window):
    assert window.stack.currentWidget() is window.welcome
    assert window.editor is None
    assert not window.act_save.isEnabled()

    window._add_tab(Document(), None, None)
    assert window.stack.currentWidget() is window.tabs
    assert window.tabs.count() == 1
    assert window.act_save.isEnabled()


def test_open_project_opens_a_tab_per_project(window, tmp_path):
    first = _write_project(tmp_path, "甲站")
    second = _write_project(tmp_path, "乙站", element_count=2)

    window.open_project(first)
    window.open_project(second)
    assert window.tabs.count() == 2
    assert window.tabs.currentIndex() == 1
    assert window.document().title == "乙站"
    assert len(window.editor.scene().layout_items()) == 2

    # 同一文件再次打开：切回已有标签页，不重复打开
    window.open_project(first)
    assert window.tabs.count() == 2
    assert window.tabs.currentIndex() == 0
    assert window.document().title == "甲站"


def test_tab_text_and_window_title_track_dirty(window, tmp_path):
    window.open_project(_write_project(tmp_path, "甲站"))
    document = window.document()
    assert window.tabs.tabText(0) == "甲站"
    assert window.windowTitle().startswith("甲站 —")

    document.mark_dirty()
    assert window.tabs.tabText(0) == "甲站 *"
    assert window.windowTitle().startswith("甲站 *")

    document.mark_clean()
    assert window.tabs.tabText(0) == "甲站"


def test_closing_tabs_falls_back_to_welcome(window, tmp_path):
    window.open_project(_write_project(tmp_path, "甲站"))
    window.open_project(_write_project(tmp_path, "乙站"))
    assert window.close_tab(1) is True
    assert window.tabs.count() == 1
    assert window.document().title == "甲站"

    assert window.close_tab(0) is True
    assert window.tabs.count() == 0
    assert window.stack.currentWidget() is window.welcome
    assert window.editor is None
    assert not window.act_save.isEnabled()


def test_close_tab_respects_user_cancel(window, monkeypatch):
    window._add_tab(Document(), None, None)
    monkeypatch.setattr(window, "_confirm_save", lambda editor: False)
    assert window.close_tab(0) is False
    assert window.tabs.count() == 1


def test_blank_unsaved_tab_is_reused(window):
    window._add_tab(Document(), None, None)
    editor = window.editor
    window._add_tab(Document(), None, None)
    assert window.tabs.count() == 1
    assert window.editor is editor

    # 当前页已有内容或已改动时，新工程必须另开一页
    window._add_tab(Document(), [registry.create_default("segment")], None)
    assert window.tabs.count() == 1  # 仍然是那个空白页被复用
    window._add_tab(Document(), None, None)
    assert window.tabs.count() == 2
    window.document().mark_dirty()
    window._add_tab(Document(), None, None)
    assert window.tabs.count() == 3


def test_edit_actions_follow_the_active_tab(window, tmp_path):
    window.open_project(_write_project(tmp_path, "甲站"))
    window.open_project(_write_project(tmp_path, "乙站"))
    first = window.tabs.widget(0)
    second = window.editor

    window.tabs.setCurrentIndex(0)
    before_first = first.view.current_scale()
    before_second = second.view.current_scale()
    window.act_zoom_in.trigger()
    assert first.view.current_scale() > before_first
    assert second.view.current_scale() == pytest.approx(before_second)

    window.act_zoom_100.trigger()
    assert first.view.current_scale() == pytest.approx(1.0)


def test_save_writes_the_active_project(window, tmp_path):
    path = _write_project(tmp_path, "甲站")
    window.open_project(path)
    window.document().title = "甲站改建"
    assert window.save_project() is True
    assert serialize.load_project(path)["document"]["title"] == "甲站改建"
    assert window.tabs.tabText(0) == "甲站改建"
    assert not window.document().is_dirty()


def test_each_tab_keeps_its_own_autosave(window):
    """每个标签页各有一份自动恢复快照，互不干扰。"""
    window._add_tab(Document(), None, None)
    first = window.editor
    first.document().mark_dirty()
    window._add_tab(Document(), None, None)
    second = window.editor
    assert second is not first
    assert window.autosave is window._autosaves[second]

    window.tabs.setCurrentIndex(0)
    assert window.autosave is window._autosaves[first]
    window.autosave.save_now()
    path = window.autosave.autosave_path()
    assert path and os.path.exists(path)

    window.autosave.clear()
    assert not os.path.exists(path)
