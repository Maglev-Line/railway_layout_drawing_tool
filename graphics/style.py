"""默认样式：正线/站线线宽颜色、车站（站台）颜色与过渡长度。

- 改「默认样式设置」窗口里的值会存到 QSettings（跨会话保留），影响**新建**图元与组合配线生成；
- 图元自身的线宽/颜色仍可在属性面板里单独改（以图元上的值为准）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from core import settings as app_settings
from ui import theme

KEY_PREFIX = "style/"


@dataclass(frozen=True)
class LineStyle:
    """一类线路的线宽与颜色。"""

    width: float
    color: str


@dataclass(frozen=True)
class Style:
    """默认样式集合。"""

    distinguish_main: bool  # 是否区分正线 / 站线（渡线等按站线变细并平滑过渡）
    main: LineStyle  # 正线
    branch: LineStyle  # 站线（组合配线生成的渡线、新线、曲股接轨端）
    taper_length: float  # 正线→站线的过渡长度（单位）
    platform_fill: str  # 车站（站台）填充色
    platform_line: str  # 车站（站台）描边色
    platform_text: str  # 车站（站台）文字色
    platform_fill2: str = theme.PLATFORM_FILL2  # 车站（站台）副色：双色填充 / 渐变用
    break_crossings: bool = False  # 新绘制的股道是否在交叉处断开（example6 的画法）


def defaults() -> Style:
    return Style(
        distinguish_main=False,
        main=LineStyle(float(theme.TRACK_WIDTH_DEFAULT), theme.TRACK_COLOR),
        branch=LineStyle(round(float(theme.TRACK_WIDTH_DEFAULT) / 2.0, 2), theme.TRACK_COLOR),
        taper_length=40.0,
        platform_fill=theme.PLATFORM_FILL,
        platform_fill2=theme.PLATFORM_FILL2,
        platform_line=theme.PLATFORM_LINE,
        platform_text=theme.PLATFORM_TEXT,
        break_crossings=False,
    )


def _read_float(settings, key: str, fallback: float, minimum: float, maximum: float) -> float:
    try:
        value = float(settings.value(KEY_PREFIX + key, fallback))
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, value))


def _read_str(settings, key: str, fallback: str) -> str:
    value = settings.value(KEY_PREFIX + key, fallback)
    return str(value or fallback)


def load() -> Style:
    """从 QSettings 读取；缺项回落到内置默认值。"""
    base = defaults()
    settings = app_settings.instance()
    distinguish = settings.value(KEY_PREFIX + "distinguish_main", base.distinguish_main)
    if isinstance(distinguish, str):
        distinguish = distinguish.lower() in ("1", "true", "yes")
    break_crossings = settings.value(KEY_PREFIX + "break_crossings", base.break_crossings)
    if isinstance(break_crossings, str):
        break_crossings = break_crossings.lower() in ("1", "true", "yes")
    return Style(
        distinguish_main=bool(distinguish),
        main=LineStyle(
            _read_float(settings, "main_width", base.main.width, 0.5, 10.0),
            _read_str(settings, "main_color", base.main.color),
        ),
        branch=LineStyle(
            _read_float(settings, "branch_width", base.branch.width, 0.5, 10.0),
            _read_str(settings, "branch_color", base.branch.color),
        ),
        taper_length=_read_float(settings, "taper_length", base.taper_length, 0.0, 500.0),
        platform_fill=_read_str(settings, "platform_fill", base.platform_fill),
        platform_fill2=_read_str(settings, "platform_fill2", base.platform_fill2),
        platform_line=_read_str(settings, "platform_line", base.platform_line),
        platform_text=_read_str(settings, "platform_text", base.platform_text),
        break_crossings=bool(break_crossings),
    )


def save(style: Style) -> None:
    settings = app_settings.instance()
    settings.setValue(KEY_PREFIX + "distinguish_main", bool(style.distinguish_main))
    settings.setValue(KEY_PREFIX + "main_width", float(style.main.width))
    settings.setValue(KEY_PREFIX + "main_color", str(style.main.color))
    settings.setValue(KEY_PREFIX + "branch_width", float(style.branch.width))
    settings.setValue(KEY_PREFIX + "branch_color", str(style.branch.color))
    settings.setValue(KEY_PREFIX + "taper_length", float(style.taper_length))
    settings.setValue(KEY_PREFIX + "platform_fill", str(style.platform_fill))
    settings.setValue(KEY_PREFIX + "platform_fill2", str(style.platform_fill2))
    settings.setValue(KEY_PREFIX + "platform_line", str(style.platform_line))
    settings.setValue(KEY_PREFIX + "platform_text", str(style.platform_text))
    settings.setValue(KEY_PREFIX + "break_crossings", bool(style.break_crossings))
    reload()


def reset() -> Style:
    """恢复内置默认并保存。"""
    style = defaults()
    save(style)
    return style


_current: Style | None = None


def current() -> Style:
    """当前生效的样式（带缓存，save/reset/reload 后刷新）。"""
    global _current
    if _current is None:
        _current = load()
    return _current


def reload() -> Style:
    global _current
    _current = load()
    return _current


# ---------------- 应用到图元 ----------------
def apply_defaults(item) -> None:
    """给新建图元套用默认样式（不覆盖已有自定义值）。"""
    style = current()
    type_id = getattr(item, "TYPE_ID", "")
    if type_id in ("segment", "turnout", "buffer_stop"):
        item.set_prop("line_width", style.main.width)
        item.set_prop("color", style.main.color)
        if type_id == "segment":
            item.set_prop("break_at_crossing", style.break_crossings)
    elif type_id == "platform":
        item.set_prop("fill_color", style.platform_fill)
        item.set_prop("fill_color2", style.platform_fill2)
        item.set_prop("line_color", style.platform_line)
        item.set_prop("text_color", style.platform_text)
    elif type_id == "connector":
        item.set_prop("line_width", style.main.width)
        item.set_prop("color", style.main.color)


def track_style(is_main: bool) -> LineStyle:
    """按是否正线取线宽颜色（不区分正线时统一用正线样式）。"""
    return line_for(current(), is_main)


def line_for(style: Style, is_main: bool) -> LineStyle:
    if style.distinguish_main and not is_main:
        return style.branch
    return style.main


def _add_change(changes: dict, item, name: str, value) -> None:
    """只在值真的变化时记录 (旧, 新)，未变化的字段不产生撤销条目。"""
    try:
        old = item.get_prop(name)
    except KeyError:
        return
    if isinstance(old, (int, float)) and isinstance(value, (int, float)):
        if abs(float(old) - float(value)) < 1e-6:
            return
    elif old == value:
        return
    changes[name] = (old, value)


def restyle_entries(items, style: Style | None = None) -> list[tuple[object, dict[str, tuple]]]:
    """把样式套到已有元素上：返回可直接交给 EditPropertiesCommand 的改动条目。

    - 股道线段：按自身「正线」标记取线宽颜色；
    - 道岔：只更新带过渡配置的曲股接轨端线宽与过渡长度（直股颜色不动）；
    - 站台：更新填充/副色/描边/文字色彩；
    - 联络线：按正线样式更新线宽颜色。
    """
    target = style or current()
    entries: list[tuple[object, dict[str, tuple]]] = []
    for item in items:
        type_id = getattr(item, "TYPE_ID", "")
        changes: dict[str, tuple] = {}
        if type_id == "segment":
            line = line_for(target, bool(item.get_prop("is_main")))
            _add_change(changes, item, "line_width", line.width)
            _add_change(changes, item, "color", line.color)
            _add_change(changes, item, "break_at_crossing", target.break_crossings)
        elif type_id == "turnout":
            if float(item.get_prop("branch_width")) > 0.0:
                _add_change(changes, item, "branch_width", target.branch.width)
                _add_change(changes, item, "taper_length", target.taper_length)
        elif type_id == "platform":
            _add_change(changes, item, "fill_color", target.platform_fill)
            _add_change(changes, item, "fill_color2", target.platform_fill2)
            _add_change(changes, item, "line_color", target.platform_line)
            _add_change(changes, item, "text_color", target.platform_text)
        elif type_id == "connector":
            line = line_for(target, True)
            _add_change(changes, item, "line_width", line.width)
            _add_change(changes, item, "color", line.color)
        if changes:
            entries.append((item, changes))
    return entries


def with_overrides(style: Style, **kwargs) -> Style:
    return replace(style, **kwargs)
