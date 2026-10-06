"""自动恢复：脏数据定时快照 + 启动检测（崩溃后可恢复）。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile

from PySide6.QtCore import QObject, QTimer

from core import serialize
from core.model import Document
from graphics.scene import LayoutScene

AUTOSAVE_DIR_NAME = "RailLayout"
INDEX_NAME = "recovery.json"
STALE_DAYS = 30
MIN_INTERVAL_S = 15


def autosave_dir() -> str:
    path = os.path.join(tempfile.gettempdir(), AUTOSAVE_DIR_NAME, "autosave")
    os.makedirs(path, exist_ok=True)
    return path


def _index_path() -> str:
    return os.path.join(autosave_dir(), INDEX_NAME)


def _read_index() -> dict:
    try:
        with open(_index_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_index(entries: list[dict]) -> None:
    try:
        with open(_index_path(), "w", encoding="utf-8") as handle:
            json.dump({"entries": entries}, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _valid_entries() -> list[dict]:
    """过滤无效/过期条目（文件不存在或超过保留期则一并删除）。"""
    kept: list[dict] = []
    now = _dt.datetime.now().timestamp()
    for entry in _read_index().get("entries", []):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("file") or "")
        if not path or not os.path.exists(path):
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if (now - mtime) > STALE_DAYS * 86400:
            _remove_file(path)
            continue
        kept.append(entry)
    return kept


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def pending_recovery() -> dict | None:
    """返回最近一次有效快照（原文件更新或不存在时才算“待恢复”）。"""
    entries = _valid_entries()
    _write_index(entries)
    best: tuple[float, dict] | None = None
    for entry in entries:
        path = str(entry.get("file") or "")
        original = str(entry.get("original") or "")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if original and os.path.exists(original):
            try:
                if os.path.getmtime(original) >= mtime:
                    continue  # 原文件更新，快照已过时
            except OSError:
                pass
        if best is None or mtime > best[0]:
            best = (mtime, entry)
    return best[1] if best else None


def discard_recovery(entry: dict) -> None:
    path = str(entry.get("file") or "")
    if path:
        _remove_file(path)
    remaining = [item for item in _valid_entries() if str(item.get("file")) != path]
    _write_index(remaining)


class AutosaveManager(QObject):
    """按文档设置定时写快照；保存/正常退出时清理。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document: Document | None = None
        self._scene: LayoutScene | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)

    def bind(self, document: Document | None, scene: LayoutScene | None) -> None:
        self._timer.stop()
        self._document = document
        self._scene = scene
        self.refresh_interval()

    def refresh_interval(self) -> None:
        if self._document is None:
            return
        interval = max(MIN_INTERVAL_S, int(self._document.autosave_interval_s or 60))
        self._timer.start(interval * 1000)

    def autosave_path(self) -> str | None:
        if self._document is None:
            return None
        return os.path.join(autosave_dir(), f"{self._document.session_id}.autosave{FILE_SUFFIX}")

    def save_now(self) -> None:
        self._write_snapshot()

    def clear(self) -> None:
        """保存或正常退出后清理当前会话快照与索引条目。"""
        if self._document is None:
            return
        path = self.autosave_path()
        if not path:
            return
        _remove_file(path)
        _write_index([item for item in _valid_entries() if str(item.get("file")) != path])

    # ---------------- 内部 ----------------
    def _on_timeout(self) -> None:
        self._write_snapshot()

    def _write_snapshot(self) -> None:
        document = self._document
        scene = self._scene
        if document is None or scene is None or not document.is_dirty():
            return
        path = self.autosave_path()
        if not path:
            return
        try:
            serialize.save_project(path, document, scene)
        except serialize.ProjectFileError:
            return
        entries = [item for item in _valid_entries() if str(item.get("file")) != path]
        entries.append(
            {
                "file": path,
                "original": document.file_path or "",
                "title": document.title,
                "time": _dt.datetime.now().replace(microsecond=0).isoformat(),
            }
        )
        _write_index(entries)


FILE_SUFFIX = serialize.FILE_SUFFIX
