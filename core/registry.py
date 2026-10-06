"""图元类型注册表：type_id -> 中文名 / 类 / 顺序。新增元素只需在此登记。"""
from __future__ import annotations

from dataclasses import dataclass

from graphics.items.base import LayoutItem
from graphics.items.buffer_stop_item import BufferStopItem
from graphics.items.platform_item import PlatformItem
from graphics.items.section_marker_item import SectionMarkerItem
from graphics.items.segment_item import SegmentItem
from graphics.items.text_item import TextItem
from graphics.items.turnout_item import TurnoutItem


@dataclass(frozen=True)
class ElementType:
    type_id: str
    name: str
    cls: type
    order: int


_TYPES: dict[str, ElementType] = {}

# 元素面板中展示/可放置的类型（按 order 排序）
TOOL_TYPE_IDS: tuple[str, ...] = ("segment", "turnout", "platform", "buffer_stop", "section_marker", "text")


def register(cls: type, name: str, order: int) -> ElementType:
    info = ElementType(type_id=cls.TYPE_ID, name=name, cls=cls, order=order)
    _TYPES[info.type_id] = info
    return info


def get(type_id: str) -> ElementType | None:
    return _TYPES.get(type_id)


def all_types() -> list[ElementType]:
    return sorted(_TYPES.values(), key=lambda info: info.order)


def create_default(type_id: str) -> LayoutItem:
    info = _TYPES.get(type_id)
    if info is None:
        raise KeyError(f"未知图元类型：{type_id}")
    return info.cls()


def create_element(data: dict) -> LayoutItem:
    info = _TYPES.get(str(data.get("type", "")))
    if info is None:
        raise KeyError(f"未知图元类型：{data.get('type')}")
    return info.cls.from_dict(data)


register(SegmentItem, "股道线段", 10)
register(TurnoutItem, "道岔", 20)
register(PlatformItem, "站台", 30)
register(BufferStopItem, "车挡", 40)
register(SectionMarkerItem, "区间标记", 50)
register(TextItem, "文字标注", 60)
