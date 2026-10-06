"""文档模型：工程元数据、画布设置、纸张与撤销栈。"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoStack

from core import geometry

DOC_TITLE_DEFAULT = "未命名配线图"


def _now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


@dataclass
class PaperSettings:
    """纸张设置（PdfExport 导出与画布参考框共用）。"""

    size_key: str = "A3"
    landscape: bool = True
    custom_width_mm: float = 420.0
    custom_height_mm: float = 297.0
    show_frame: bool = True

    def base_size_mm(self) -> tuple[float, float]:
        if self.size_key in geometry.PAPER_SIZES_MM:
            return geometry.PAPER_SIZES_MM[self.size_key]
        return self.custom_width_mm, self.custom_height_mm

    def size_mm(self) -> tuple[float, float]:
        w, h = self.base_size_mm()
        return (h, w) if self.landscape else (w, h)

    def size_units(self) -> tuple[float, float]:
        w, h = self.size_mm()
        return geometry.mm_to_units(w), geometry.mm_to_units(h)

    def describe(self) -> str:
        w, h = self.size_mm()
        name = self.size_key if self.size_key in geometry.PAPER_SIZES_MM else "自定义"
        orient = "横向" if self.landscape else "纵向"
        return f"{name} {orient} {w:.0f}×{h:.0f} mm"

    def to_dict(self) -> dict:
        return {
            "size_key": self.size_key,
            "landscape": bool(self.landscape),
            "custom_width_mm": float(self.custom_width_mm),
            "custom_height_mm": float(self.custom_height_mm),
            "show_frame": bool(self.show_frame),
        }

    def apply_dict(self, data: dict) -> None:
        data = data or {}
        self.size_key = str(data.get("size_key", self.size_key))
        self.landscape = bool(data.get("landscape", self.landscape))
        self.custom_width_mm = float(data.get("custom_width_mm", self.custom_width_mm))
        self.custom_height_mm = float(data.get("custom_height_mm", self.custom_height_mm))
        self.show_frame = bool(data.get("show_frame", self.show_frame))


class Document(QObject):
    """一份配线图工程：设置 + 撤销栈 + 文件状态。"""

    dirtyChanged = Signal(bool)
    settingsChanged = Signal()

    ANGLE_STEPS = (0.0, 15.0, 30.0, 45.0, 90.0)
    GRID_STEPS = (5.0, 10.0, 20.0, 25.0, 50.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._recompute_dirty)

        self.session_id = uuid4().hex[:12]
        self.file_path: str | None = None
        self.title = DOC_TITLE_DEFAULT
        self.station = ""
        self.created_at = _now_iso()
        self.modified_at = self.created_at

        # 画布设置
        self.grid_size = 10.0
        self.show_grid = True
        self.snap_grid = True
        self.snap_ports = True
        self.angle_step = 15.0
        self.autosave_interval_s = 60
        self.paper = PaperSettings()

        self._manual_dirty = False
        self._dirty = False

    # ---------------- 脏标记 ----------------
    def is_dirty(self) -> bool:
        return self._dirty

    def _recompute_dirty(self) -> None:
        dirty = self._manual_dirty or not self.undo_stack.isClean()
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirtyChanged.emit(dirty)

    def mark_dirty(self) -> None:
        self._manual_dirty = True
        self._recompute_dirty()

    def mark_clean(self) -> None:
        self._manual_dirty = False
        self.undo_stack.setClean()
        self._recompute_dirty()

    def touch(self) -> None:
        self.modified_at = _now_iso()

    def notify_settings_changed(self) -> None:
        self.mark_dirty()
        self.settingsChanged.emit()

    # ---------------- 序列化 ----------------
    def settings_dict(self) -> dict:
        return {
            "title": self.title,
            "station": self.station,
            "created": self.created_at,
            "modified": self.modified_at,
            "grid_size": self.grid_size,
            "show_grid": self.show_grid,
            "snap_grid": self.snap_grid,
            "snap_ports": self.snap_ports,
            "angle_step": self.angle_step,
            "autosave_interval_s": self.autosave_interval_s,
            "paper": self.paper.to_dict(),
        }

    def apply_settings_dict(self, data: dict) -> None:
        data = data or {}
        self.title = str(data.get("title") or DOC_TITLE_DEFAULT)
        self.station = str(data.get("station") or "")
        self.created_at = str(data.get("created") or self.created_at)
        self.modified_at = str(data.get("modified") or self.modified_at)
        self.grid_size = float(data.get("grid_size", self.grid_size) or self.grid_size)
        self.show_grid = bool(data.get("show_grid", self.show_grid))
        self.snap_grid = bool(data.get("snap_grid", self.snap_grid))
        self.snap_ports = bool(data.get("snap_ports", self.snap_ports))
        self.angle_step = float(data.get("angle_step", self.angle_step))
        self.autosave_interval_s = int(data.get("autosave_interval_s", self.autosave_interval_s) or 60)
        self.paper.apply_dict(data.get("paper") or {})
