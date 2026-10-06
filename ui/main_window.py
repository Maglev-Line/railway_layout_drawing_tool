"""主窗口：菜单/工具栏、欢迎页与工作页切换、文件动作与自动恢复。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStyle,
    QToolBar,
)

from core import autosave, pdf_export, serialize, settings
from core.model import Document
from graphics import style as style_module
from ui import icons, theme
from ui.dialogs.export_pdf_dialog import ExportPdfDialog
from ui.dialogs.new_project_dialog import NewProjectDialog
from ui.dialogs.recovery_dialog import CHOICE_RECOVER, RecoveryDialog, show_shortcuts
from ui.dialogs.style_dialog import StyleDialog
from ui.editor_page import NUDGE_FINE, EditorPage, ROTATE_STEP_DEFAULT
from ui.welcome_page import WelcomePage

STATUS_MESSAGE_MS = 5000
CREDIT_TEXT = "制作：磁浮线"


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("铁路配线图绘制器")
        self.setWindowIcon(icons.app_icon())
        self.resize(1280, 820)

        self._document: Document | None = None

        self.welcome = WelcomePage(self)
        self.editor = EditorPage(self)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.editor)
        self.setCentralWidget(self.stack)

        self.autosave = autosave.AutosaveManager(self)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()

        self.welcome.newRequested.connect(self.new_project)
        self.welcome.openRequested.connect(self.open_project_dialog)
        self.welcome.recentRequested.connect(self.open_project)
        self.editor.statusMessage.connect(self._show_message)
        self.editor.cursorMoved.connect(self._on_cursor_moved)
        self.editor.zoomChanged.connect(self._on_zoom_changed)

        self._refresh_recent()
        self._update_page()
        QTimer.singleShot(0, self._check_recovery)

    # ---------------- 界面搭建 ----------------
    def _make_action(self, text, slot, shortcut=None, icon=None, tip="") -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(icon)
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                action.setShortcuts([QKeySequence(item) for item in shortcut])
            else:
                action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setStatusTip(tip)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        style = self.style()
        icon_new = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        icon_open = style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        icon_save = style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        icon_export = style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        icon_undo = style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        icon_redo = style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward)

        self.act_new = self._make_action("新建工程…", self.new_project, "Ctrl+N", icon_new, "新建一份配线图工程")
        self.act_open = self._make_action("打开工程…", self.open_project_dialog, "Ctrl+O", icon_open, "打开 .rld 工程文件")
        self.act_save = self._make_action("保存", self.save_project, "Ctrl+S", icon_save, "保存到当前工程文件")
        self.act_save_as = self._make_action("另存为…", self.save_project_as, "Ctrl+Shift+S")
        self.act_export = self._make_action("导出 PDF…", self.export_pdf, "Ctrl+P", icon_export, "导出矢量 PDF")
        self.act_quit = self._make_action("退出", self.close, None)

        self.act_undo = self._make_action("撤销", self.undo, "Ctrl+Z", icon_undo)
        self.act_redo = self._make_action("重做", self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"], icon_redo)
        self.act_cut = self._make_action("剪切", self.cut_selected, "Ctrl+X")
        self.act_copy = self._make_action("复制", self.editor.copy_selected, "Ctrl+C")
        self.act_paste = self._make_action("粘贴", self.editor.paste, "Ctrl+V")
        self.act_duplicate = self._make_action("再制", self.editor.duplicate_selected, "Ctrl+D")
        self.act_delete = self._make_action("删除", self.editor.delete_selected, ["Delete", "Backspace"])
        self.act_select_all = self._make_action("全选", self.editor.select_all, "Ctrl+A")

        self.act_rotate_ccw = self._make_action("逆时针旋转", lambda: self._rotate(-1.0), "R")
        self.act_rotate_cw = self._make_action("顺时针旋转", lambda: self._rotate(1.0), "Shift+R")
        self.act_flip = self._make_action("翻转", self.editor.flip_selected, "F")
        self.act_cancel = self._make_action("取消当前操作", self.editor.cancel_tool, "Esc")

        self.act_zoom_in = self._make_action("放大", self.editor.zoom_in, ["Ctrl+=", "Ctrl++"])
        self.act_zoom_out = self._make_action("缩小", self.editor.zoom_out, "Ctrl+-")
        self.act_zoom_100 = self._make_action("缩放 100%", self.editor.zoom_reset, "Ctrl+0")
        self.act_zoom_fit = self._make_action("适配窗口", self.editor.zoom_fit, "Ctrl+9")
        self.act_nudge_left = self._make_action("左移", lambda: self._nudge(-1.0, 0.0), "Left")
        self.act_nudge_right = self._make_action("右移", lambda: self._nudge(1.0, 0.0), "Right")
        self.act_nudge_up = self._make_action("上移", lambda: self._nudge(0.0, -1.0), "Up")
        self.act_nudge_down = self._make_action("下移", lambda: self._nudge(0.0, 1.0), "Down")

        self.act_shortcuts = self._make_action("快捷键说明", lambda: show_shortcuts(self), "F1")
        self.act_style = self._make_action("默认样式…", self.open_style_dialog, "Ctrl+,", None, "设置正线/站线线宽颜色、车站颜色等默认样式")
        self.act_about = self._make_action("关于", self.show_about, None)

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        self._recent_menu = file_menu.addMenu("最近打开")
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export)
        file_menu.addSeparator()
        file_menu.addAction(self.act_style)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = menu_bar.addMenu("编辑(&E)")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_cut)
        edit_menu.addAction(self.act_copy)
        edit_menu.addAction(self.act_paste)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_delete)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_select_all)

        element_menu = menu_bar.addMenu("元素(&M)")
        element_menu.addAction(self.act_rotate_ccw)
        element_menu.addAction(self.act_rotate_cw)
        element_menu.addAction(self.act_flip)
        element_menu.addSeparator()
        element_menu.addAction(self.act_cancel)

        view_menu = menu_bar.addMenu("视图(&V)")
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_zoom_100)
        view_menu.addAction(self.act_zoom_fit)

        help_menu = menu_bar.addMenu("帮助(&H)")
        help_menu.addAction(self.act_shortcuts)
        help_menu.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.addAction(self.act_new)
        toolbar.addAction(self.act_open)
        toolbar.addAction(self.act_save)
        toolbar.addSeparator()
        toolbar.addAction(self.act_undo)
        toolbar.addAction(self.act_redo)
        toolbar.addSeparator()
        toolbar.addAction(self.act_export)
        toolbar.addSeparator()
        toolbar.addAction(self.act_zoom_fit)
        self.addToolBar(toolbar)

    def _build_statusbar(self) -> None:
        self._coord_label = QLabel("坐标 —")
        self._coord_label.setMinimumWidth(260)
        self._zoom_label = QLabel("缩放 100%")
        self._zoom_label.setMinimumWidth(90)
        self._credit_label = QLabel(CREDIT_TEXT)
        self._credit_label.setStyleSheet(theme.FAINT_QSS)
        self._credit_label.setContentsMargins(9, 0, 6, 0)
        self._credit_label.setToolTip(CREDIT_TEXT)
        self.statusBar().addPermanentWidget(self._coord_label)
        self.statusBar().addPermanentWidget(self._zoom_label)
        self.statusBar().addPermanentWidget(self._credit_label)

    # ---------------- 页面与标题 ----------------
    def _update_page(self) -> None:
        self.stack.setCurrentWidget(self.editor if self._document is not None else self.welcome)

    def _update_title(self, *_args) -> None:
        document = self._document
        if document is None:
            self.setWindowTitle("铁路配线图绘制器")
            return
        star = " *" if document.is_dirty() else ""
        self.setWindowTitle(f"{document.title}{star} — 铁路配线图绘制器")

    def _update_edit_actions(self, *_args) -> None:
        document = self._document
        has_doc = document is not None
        stack = document.undo_stack if document is not None else None
        self.act_undo.setEnabled(bool(has_doc and stack.canUndo()))
        self.act_undo.setText(f"撤销 {stack.undoText()}" if has_doc and stack.undoText() else "撤销")
        self.act_redo.setEnabled(bool(has_doc and stack.canRedo()))
        self.act_redo.setText(f"重做 {stack.redoText()}" if has_doc and stack.redoText() else "重做")
        for action in (
            self.act_save,
            self.act_save_as,
            self.act_export,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_duplicate,
            self.act_delete,
            self.act_select_all,
            self.act_rotate_ccw,
            self.act_rotate_cw,
            self.act_flip,
        ):
            action.setEnabled(has_doc)

    # ---------------- 文档绑定 ----------------
    def _bind_document(self, document: Document, items, file_path: str | None) -> None:
        self._unbind_document()
        self._document = document
        document.file_path = file_path
        self.editor.reload_document(document, items)
        document.mark_clean()
        self.autosave.bind(document, self.editor.scene())

        document.dirtyChanged.connect(self._update_title)
        document.settingsChanged.connect(self._on_settings_changed)
        stack = document.undo_stack
        stack.canUndoChanged.connect(self._update_edit_actions)
        stack.canRedoChanged.connect(self._update_edit_actions)
        stack.indexChanged.connect(self._update_edit_actions)

        if file_path:
            settings.add_recent_file(file_path)
            self._refresh_recent()
        self._update_title()
        self._update_edit_actions()
        self._update_page()

    def _unbind_document(self) -> None:
        document = self._document
        if document is None:
            return
        self.autosave.clear()
        self.autosave.bind(None, None)
        for signal, slot in (
            (document.dirtyChanged, self._update_title),
            (document.settingsChanged, self._on_settings_changed),
            (document.undo_stack.canUndoChanged, self._update_edit_actions),
            (document.undo_stack.canRedoChanged, self._update_edit_actions),
            (document.undo_stack.indexChanged, self._update_edit_actions),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._document = None

    def _on_settings_changed(self) -> None:
        self.autosave.refresh_interval()
        self._update_title()

    # ---------------- 文件动作 ----------------
    def new_project(self) -> None:
        if not self._maybe_save():
            return
        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        document = Document()
        document.title = values["title"]
        document.grid_size = values["grid_size"]
        paper = document.paper
        paper.size_key = values["page_key"]
        paper.landscape = values["landscape"]
        paper.custom_width_mm = values["custom_width_mm"]
        paper.custom_height_mm = values["custom_height_mm"]
        paper.show_frame = values["show_frame"]
        self._bind_document(document, None, None)
        self._show_message("已新建工程：从左侧选择工具开始绘制")

    def open_project_dialog(self) -> None:
        if not self._maybe_save():
            return
        path, _filter = QFileDialog.getOpenFileName(
            self, "打开工程", settings.last_directory(), serialize.FILE_FILTER
        )
        if path:
            self.open_project(path, guard=False)

    def open_project(self, path: str, guard: bool = True) -> None:
        if guard and not self._maybe_save():
            return
        try:
            data = serialize.load_project(path)
            items = serialize.build_items(data)
        except serialize.ProjectFileError as error:
            QMessageBox.warning(self, "打开工程失败", str(error))
            self._show_message("打开失败：文件无效或不可读")
            return
        document = Document()
        serialize.apply_document_settings(document, data)
        self._bind_document(document, items, path)
        self._show_message(f"已打开：{os.path.basename(path)}")

    def save_project(self) -> bool:
        return self._save(save_as=False)

    def save_project_as(self) -> bool:
        return self._save(save_as=True)

    def _save(self, save_as: bool) -> bool:
        document = self._document
        scene = self.editor.scene()
        if document is None or scene is None:
            return False
        path = document.file_path
        if save_as or not path:
            suggested = path or os.path.join(
                settings.last_directory() or "",
                f"{document.title}{serialize.FILE_SUFFIX}",
            )
            path, _filter = QFileDialog.getSaveFileName(self, "保存工程", suggested, serialize.FILE_FILTER)
            if not path:
                return False
            if not path.lower().endswith((".rld", ".json")):
                path += serialize.FILE_SUFFIX
        try:
            serialize.save_project(path, document, scene)
        except serialize.ProjectFileError as error:
            QMessageBox.warning(self, "保存失败", str(error))
            return False
        document.file_path = path
        document.mark_clean()
        self.autosave.clear()
        settings.add_recent_file(path)
        self._refresh_recent()
        self._update_title()
        self._show_message(f"已保存：{path}")
        return True

    def export_pdf(self) -> None:
        document = self._document
        scene = self.editor.scene()
        if document is None or scene is None:
            return
        default_dir = settings.last_directory() or os.path.expanduser("~")
        default_path = os.path.join(default_dir, f"{document.title}.pdf")
        dialog = ExportPdfDialog(default_path, document.paper.size_key, document.paper.landscape, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        path = dialog.file_path()
        view = self.editor.view
        view_rect = None
        if options.scope == "view":
            view_rect = view.mapToScene(view.viewport().rect()).boundingRect()
        try:
            plan = pdf_export.plan_export(scene, document, options, view_rect)
        except pdf_export.ExportError as error:
            QMessageBox.warning(self, "导出 PDF 失败", str(error))
            return
        if not plan.fits:
            box = QMessageBox(self)
            box.setWindowTitle("内容超出纸张")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText("按 100% 原始尺寸导出时内容超出纸张，超出部分会被裁切。")
            box.setInformativeText("可返回改用「自动适配纸张」，或继续按 100% 导出。")
            keep = box.addButton("继续导出", QMessageBox.ButtonRole.DestructiveRole)
            back = box.addButton("返回修改", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(back)
            box.exec()
            if box.clickedButton() is not keep:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pdf_export.export_pdf(path, scene, document, options, view_rect)
        except pdf_export.ExportError as error:
            QMessageBox.warning(self, "导出 PDF 失败", str(error))
            return
        except OSError as error:
            QMessageBox.warning(
                self, "导出 PDF 失败", f"写入失败：{error}\n请检查目标目录权限或文件名后重试。"
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        settings.set_last_directory(os.path.dirname(path))
        self._show_message(f"已导出 PDF：{path}")

    def _maybe_save(self) -> bool:
        document = self._document
        if document is None or not document.is_dirty():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("保存更改")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"「{document.title}」有未保存的更改。")
        box.setInformativeText("保存后可用「打开工程」继续编辑；选择「不保存」将丢弃本次更改。")
        save_button = box.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(save_button)
        discard_button = box.addButton("不保存", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return self._save(save_as=self._document is not None and not self._document.file_path)
        if clicked is discard_button:
            self.autosave.clear()
            return True
        return False

    # ---------------- 恢复 ----------------
    def _check_recovery(self) -> None:
        entry = autosave.pending_recovery()
        if entry is None:
            return
        dialog = RecoveryDialog(entry, self)
        dialog.exec()
        if dialog.choice == CHOICE_RECOVER:
            self._recover(entry)
        else:
            autosave.discard_recovery(entry)
            self._show_message("已丢弃恢复快照")

    def _recover(self, entry: dict) -> None:
        path = str(entry.get("file") or "")
        try:
            data = serialize.load_project(path)
            items = serialize.build_items(data)
        except serialize.ProjectFileError as error:
            QMessageBox.warning(self, "恢复失败", str(error))
            autosave.discard_recovery(entry)
            return
        document = Document()
        serialize.apply_document_settings(document, data)
        self._bind_document(document, items, str(entry.get("original") or "") or None)
        document.mark_dirty()
        autosave.discard_recovery(entry)
        self.autosave.save_now()
        self._show_message("已恢复未保存的工程：请检查内容后保存")

    # ---------------- 编辑动作 ----------------
    def undo(self) -> None:
        self.editor.finish_chain()
        if self._document is not None:
            self._document.undo_stack.undo()

    def redo(self) -> None:
        self.editor.finish_chain()
        if self._document is not None:
            self._document.undo_stack.redo()

    def cut_selected(self) -> None:
        self.editor.copy_selected()
        self.editor.delete_selected()

    def _rotate(self, sign: float) -> None:
        document = self._document
        step = document.angle_step if document is not None and document.angle_step > 0 else ROTATE_STEP_DEFAULT
        self.editor.rotate_selected(sign * step)

    def _nudge(self, dx: float, dy: float) -> None:
        document = self._document
        if document is None:
            return
        step = document.grid_size if (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier) else NUDGE_FINE
        self.editor.nudge_selected(dx * step, dy * step)

    # ---------------- 杂项 ----------------
    def _refresh_recent(self) -> None:
        files = settings.recent_files()
        self.welcome.set_recent_files(files)
        self._recent_menu.clear()
        if not files:
            placeholder = self._recent_menu.addAction("（暂无记录）")
            placeholder.setEnabled(False)
            return
        for path in files:
            action = self._recent_menu.addAction(path)
            action.triggered.connect(lambda _checked=False, p=path: self.open_project(p))
        self._recent_menu.addSeparator()
        clear_action = self._recent_menu.addAction("清除记录")
        clear_action.triggered.connect(self._clear_recent)

    def _clear_recent(self) -> None:
        settings.clear_recent_files()
        self._refresh_recent()

    # ---------------- 默认样式 ----------------
    def open_style_dialog(self) -> None:
        dialog = StyleDialog(self, self.editor.apply_style)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        style_module.save(dialog.values())
        self._show_message("默认样式已保存：新建元素与自动生成的组合配线会按新样式绘制")

    def _show_message(self, message: str) -> None:
        self.statusBar().showMessage(message, STATUS_MESSAGE_MS)

    def _on_cursor_moved(self, pos) -> None:
        from core import geometry

        self._coord_label.setText(
            f"坐标 X {pos.x():.1f} Y {pos.y():.1f} 单位"
            f"（{geometry.units_to_mm(pos.x()):.0f}, {geometry.units_to_mm(pos.y()):.0f} mm）"
        )

    def _on_zoom_changed(self, scale: float) -> None:
        self._zoom_label.setText(f"缩放 {scale * 100:.0f}%")

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于",
            "铁路配线图绘制器 v1.0\n\n"
            "用于绘制车站股道、道岔、站台与车挡等配线元素：\n"
            "· 自由绘制 + 吸附（网格 / 端点 / 道岔端口 / 角度）\n"
            "· 工程文件 .rld（JSON 明文），支持自动恢复快照\n"
            "· 一键导出矢量 PDF",
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._maybe_save():
            event.ignore()
            return
        # 断开文档信号：窗口与文档析构顺序不定，避免析构期信号回调告警
        self._unbind_document()
        event.accept()
