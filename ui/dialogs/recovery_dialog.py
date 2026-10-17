"""恢复提示对话框：检测到未正常保存的快照时询问用户。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from ui import theme

CHOICE_RECOVER = "recover"
CHOICE_DISCARD = "discard"


class RecoveryDialog(QDialog):
    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("恢复未保存的工程")
        self.setModal(True)
        self.choice = CHOICE_DISCARD

        title = QLabel("检测到上次未正常保存的工程", self)
        title.setStyleSheet(theme.CARD_TITLE_QSS)

        original = str(entry.get("original") or "") or "（尚未保存过）"
        info = QLabel(
            f"图名：{entry.get('title') or '未命名配线图'}\n"
            f"快照时间：{entry.get('time') or '—'}\n"
            f"原文件：{original}",
            self,
        )
        info.setWordWrap(True)

        hint = QLabel(
            "选择「恢复工程」会把快照内容载入画布（请随后保存）；选择「丢弃快照」将删除该恢复数据。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)

        recover = theme.ok_button("恢复工程", self)
        recover.setDefault(True)
        recover.clicked.connect(self._on_recover)
        discard = theme.cancel_button("丢弃快照", self)
        discard.clicked.connect(self._on_discard)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(recover)
        buttons.addWidget(discard)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(hint)
        layout.addLayout(buttons)

    def _on_recover(self) -> None:
        self.choice = CHOICE_RECOVER
        self.accept()

    def _on_discard(self) -> None:
        answer = QMessageBox.question(
            self,
            "丢弃快照",
            "确定要删除这份恢复数据吗？删除后无法再找回未保存的内容。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.choice = CHOICE_DISCARD
            self.accept()


SHORTCUTS_TEXT = """\
绘制：V 选择 · L 股道线段 · T 单开道岔 · P 站台 · B 车挡 · M 区间标记 · X 文字标注
道岔：面板选单开/双开/三开/交分；两步放置——先点主线位置，再拖出曲股方向
组合：单渡线 / 交叉渡线 / 存车线 / 折返线——依次点两条平行股道，移动鼠标定方向，再点一次生成
站台：岛式站台——依次点两条平行股道，移动鼠标定位置，再点一次在中间生成（两侧留默认间隔）
联络线：直线 / 曲线——依次点两条交叉股道，移动鼠标定接点，再点一次生成（不改动原有股道）
编辑：Ctrl+Z 撤销 · Ctrl+Y 重做 · Ctrl+C/V 复制/粘贴 · Ctrl+D 再制 · Delete 删除 · Ctrl+A 全选
元素：R 逆时针旋转 · Shift+R 顺时针旋转 · F 翻转道岔 · 方向键微调（Shift 按网格步长）
绘制中：按住 Shift 临时脱离角度吸附 · 右键/Esc 结束当前操作
视图：Ctrl+滚轮 缩放 · 空格+拖拽 或 中键拖拽 平移 · Ctrl+0 缩放 100% · Ctrl+9 适配窗口
文件：Ctrl+N 新建 · Ctrl+O 打开 · Ctrl+S 保存 · Ctrl+Shift+S 另存为 · Ctrl+W 关闭当前工程 · Ctrl+P 导出 PDF
多工程：每份工程一个标签页（标签可拖动排序、点 × 关闭），全部关闭后回到欢迎页
指引：绘制时右侧显示步骤提示、当前锚定到的元素与其余可参照元素（点击可定位）
样式：Ctrl+, 默认样式（正线/站线线宽颜色、车站填充/副色、过渡长度、股道交叉处断开）
"""


def show_shortcuts(parent) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle("快捷键")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText("常用快捷键")
    box.setInformativeText(SHORTCUTS_TEXT)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()
