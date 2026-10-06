"""共享 UI 视觉令牌与通用控件样式：颜色/字号集中在此，界面代码只引用常量与工厂。

规范来源：项目根目录 ui.md（浅色桌面应用 · Qt Widgets）。
新增样式时必须先在本模块登记令牌，禁止在界面/图元代码里写颜色、字号字面量。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

# ---------------- 主色板 ----------------
ACCENT = "#1a73e8"
ACCENT_TEXT = "#ffffff"
PANEL_BG = "#f5f5f5"
BORDER = "#cccccc"
ROW_ACTIVE = "#BADEFF"
WARN = "#c0392b"

# ---------------- 灰阶 ----------------
GRAY_STRONG = "#555555"
GRAY = "#666666"
GRAY_MID = "#777777"
GRAY_WEAK = "#888888"
GRAY_FAINT = "#999999"

# ---------------- 字号 ----------------
FONT_TITLE = "26pt"
FONT_CTA = "15pt"
FONT_STAT = "12pt"
FONT_CARD_TITLE = "11pt"
FONT_HINT = "8.5pt"
FONT_TINY = "8pt"

# ---------------- 画布与图元令牌 ----------------
CANVAS_BG = "#ffffff"
GRID_MINOR = "#eef1f3"
GRID_MAJOR = "#dfe4e8"
PAPER_FRAME = "#b9c0c6"
TRACK_COLOR = "#000000"
MARKER_FILL_BRIDGE = "#f7f7f7"
MARKER_FILL_TUNNEL = "#e3e6e8"
PLATFORM_FILL = "#e53935"
PLATFORM_LINE = "#000000"
PLATFORM_TEXT = "#ffffff"
LABEL_COLOR = GRAY_STRONG

# 图元默认尺寸/字号（单位：场景单位 = 96dpi 像素）
TRACK_WIDTH_DEFAULT = 4.0
LABEL_SIZE = 9.0
TEXT_SIZE_DEFAULT = 10.0

# 线型令牌：名称 -> Qt 画笔样式
PEN_STYLES = {
    "实线": Qt.PenStyle.SolidLine,
    "虚线": Qt.PenStyle.DashLine,
    "点线": Qt.PenStyle.DotLine,
}

# 区间标记预设：样式名 -> (填充色或 None 表示不填充, 线型名)
MARKER_PRESETS = {
    "桥梁": (MARKER_FILL_BRIDGE, "实线"),
    "隧道": (MARKER_FILL_TUNNEL, "虚线"),
    "路堑": (None, "实线"),
    "路堤": (None, "虚线"),
    "自定义": (None, "实线"),
}

# ---------------- 常用样式 ----------------
CTA_QSS = (
    f"font-size:{FONT_CTA};font-weight:bold;padding:10px;"
    f"background:{ACCENT};color:{ACCENT_TEXT};border-radius:8px;"
)
CTA_OUTLINE_QSS = (
    f"font-size:{FONT_CTA};font-weight:bold;padding:10px;"
    f"background:#ffffff;color:{ACCENT};"
    f"border:2px solid {ACCENT};border-radius:8px;"
)
OK_BUTTON_QSS = "font-weight:bold;min-width:88px;"
HINT_QSS = f"color:{GRAY};font-size:{FONT_HINT};"
FAINT_QSS = f"color:{GRAY_FAINT};font-size:{FONT_TINY};"
TITLE_QSS = f"font-size:{FONT_TITLE};font-weight:bold;"
SUBTITLE_QSS = f"color:{GRAY};"
CARD_TITLE_QSS = f"font-size:{FONT_CARD_TITLE};font-weight:bold;color:{GRAY_STRONG};"
GROUP_LABEL_QSS = f"font-size:{FONT_HINT};font-weight:bold;color:{GRAY};"
INFO_BOX_QSS = f"background:{PANEL_BG};padding:6px;"
CARD_QSS = f"QFrame{{background:#ffffff;border:1px solid {BORDER};border-radius:4px;}}"
PANEL_QSS = f"QFrame#sidePanel{{background:{PANEL_BG};border:1px solid {BORDER};border-radius:4px;}}"


def big_button(text: str, parent=None, *, outline: bool = False) -> QPushButton:
    """页面级大号主/副按钮。"""
    btn = QPushButton(text, parent)
    btn.setMinimumSize(280, 96)
    btn.setStyleSheet(CTA_OUTLINE_QSS if outline else CTA_QSS)
    return btn


def ok_button(text: str = "确定", parent=None) -> QPushButton:
    """对话框主按钮：加粗 + 最小宽度（记得再调 setDefault(True)）。"""
    btn = QPushButton(text, parent)
    btn.setStyleSheet(OK_BUTTON_QSS)
    return btn


def cancel_button(text: str = "取消", parent=None) -> QPushButton:
    return QPushButton(text, parent)
