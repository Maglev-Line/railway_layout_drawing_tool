"""撤销/重做命令：添加、删除与属性编辑（移动/改尺寸/改样式都走属性编辑）。"""
from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class AddItemsCommand(QUndoCommand):
    """把图元加入场景；undo 时移除（对象仍被命令持有，可再次 redo）。"""

    def __init__(self, scene, items, text: str = "添加元素"):
        super().__init__(text)
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            if item.scene() is not self._scene:
                self._scene.addItem(item)
        self._scene.notify_items_changed(self._items)

    def undo(self) -> None:
        for item in self._items:
            item.setSelected(False)
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._scene.notify_items_changed(self._items)


class RemoveItemsCommand(QUndoCommand):
    """删除图元（保留对象引用，便于撤销恢复）。"""

    def __init__(self, scene, items, text: str = "删除元素"):
        super().__init__(text)
        self._scene = scene
        self._items = list(items)

    def redo(self) -> None:
        for item in self._items:
            item.setSelected(False)
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._scene.notify_items_changed(self._items)

    def undo(self) -> None:
        for item in self._items:
            if item.scene() is not self._scene:
                self._scene.addItem(item)
        self._scene.notify_items_changed(self._items)


class EditPropertiesCommand(QUndoCommand):
    """批量属性修改；同一 merge_key 的连续命令会合并（如方向键微调、拖动过程）。"""

    def __init__(self, scene, entries, text: str = "修改属性", merge_key: str | None = None):
        super().__init__(text)
        self._scene = scene
        self._entries: list[tuple[object, dict[str, list]]] = [
            (item, {name: [old, new] for name, (old, new) in props.items()})
            for item, props in entries
        ]
        self._merge_key = merge_key

    def _notify(self) -> None:
        self._scene.notify_items_changed([item for item, _ in self._entries])

    def redo(self) -> None:
        for item, props in self._entries:
            for name, pair in props.items():
                item.set_prop(name, pair[1])
            item.update()
        self._notify()

    def undo(self) -> None:
        for item, props in reversed(self._entries):
            for name, pair in props.items():
                item.set_prop(name, pair[0])
            item.update()
        self._notify()

    def id(self) -> int:
        if not self._merge_key or not self._entries:
            return -1
        key = (self._merge_key, tuple(sorted(id(item) for item, _ in self._entries)))
        return abs(hash(key)) % 2_000_000_000 or -1

    def mergeWith(self, other: QUndoCommand) -> bool:  # noqa: N802 (Qt 命名)
        if not isinstance(other, EditPropertiesCommand):
            return False
        if self._merge_key is None or other._merge_key != self._merge_key:
            return False
        if len(other._entries) != len(self._entries):
            return False
        for (item_a, props_a), (item_b, props_b) in zip(self._entries, other._entries):
            if item_a is not item_b or set(props_a) != set(props_b):
                return False
            for name in props_a:
                props_a[name][1] = props_b[name][1]
        return True
