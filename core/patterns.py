"""配线组合生成：由两条股道自动生成渡线 / 存车线 / 折返线（纯计算，输出图元字典）。

局部坐标：以第一条股道 A 的起点为原点，u = A 的方向，v = A→B 的法向。
所有几何先在 (t, v) 里算好，再换算回场景坐标；输出的字典可直接交给
``registry.create_element`` 实例化，也方便在测试里断言。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF

from core import geometry, platform, turnout

PATTERN_LABELS: tuple[tuple[str, str], ...] = (
    ("crossover_single", "单渡线"),
    ("crossover_double", "交叉渡线"),
    ("siding", "存车线"),
    ("turnback", "折返线"),
    ("island_platform", "岛式站台"),
)
PATTERN_IDS: tuple[str, ...] = tuple(kind for kind, _ in PATTERN_LABELS)
PATTERN_NAMES: dict[str, str] = dict(PATTERN_LABELS)

MAX_SKEW = 20.0  # 两条股道方向夹角上限
MIN_SPACING = 12.0  # 两条股道间距下限
TURNOUT_KIND = "single_right"  # 组合内统一用右开道岔，靠 mirror 翻转
BRANCH_ANGLE_TARGET = 45.0  # 目标分支角（示例图里的紧凑斜线）
NEW_LINE_RATIO = 0.5  # 新线长度 = 所选股道长度 × 该比例（再按需放大）
BUFFER_WIDTH = 26.0  # 生成车挡的挡板宽度


class PatternError(ValueError):
    """组合无法生成（股道不平行、间距太小等）。"""


def name_of(kind: str) -> str:
    return PATTERN_NAMES.get(kind, kind)


@dataclass(frozen=True)
class Track:
    """股道中心线：起点（场景坐标）、方向角（度）与长度，附带自身线宽/颜色。"""

    origin: QPointF
    angle: float
    length: float
    width: float = 0.0  # 0 = 用图元默认
    color: str = ""

    def point(self, t: float) -> QPointF:
        return geometry.point_from(self.origin, self.angle, t)

    @property
    def end(self) -> QPointF:
        return self.point(self.length)


@dataclass(frozen=True)
class LinePaint:
    """条线的绘制参数（0 / 空表示用图元默认值）。"""

    width: float = 0.0
    color: str = ""


@dataclass(frozen=True)
class PatternStyle:
    """区分正线时用：渡线/新线等非正线部件的线宽、颜色与过渡长度。"""

    branch_width: float = 0.0  # 曲股接轨端线宽（站线），0 = 与股道一致（不变细）
    new_line_width: float = 0.0  # 新生成股道的线宽
    new_line_color: str = ""
    taper_length: float = 0.0  # 正线→站线的过渡长度
    # 岛式站台的默认配色（空值 = 用图元自带默认）
    platform_fill: str = ""
    platform_fill2: str = ""
    platform_line: str = ""
    platform_text: str = ""


@dataclass(frozen=True)
class Frame:
    """两条股道构成的局部坐标系。"""

    origin: QPointF  # 对应局部 (0, 0)
    u_angle: float  # u 轴（沿 A）的场景角度
    v_angle: float  # v 轴（A 指向 B）的场景角度
    spacing: float  # 两条股道的法向间距
    b_angle: float  # B 的方向角（略带夹角时保证端口贴合）

    def point(self, t: float, v: float) -> QPointF:
        base = geometry.point_from(self.origin, self.u_angle, t)
        return geometry.point_from(base, self.v_angle, v)


def make_frame(a: Track, b: Track) -> Frame:
    """由两条股道构造局部坐标系；不平行或太近时抛 PatternError。"""
    if abs(geometry.signed_angle_diff(b.angle, a.angle)) > MAX_SKEW:
        raise PatternError("请选择两条方向大致相同的股道")
    probe = b.point(b.length / 2.0)
    rel = QPointF(probe.x() - a.origin.x(), probe.y() - a.origin.y())
    ux, uy = math.cos(math.radians(a.angle)), math.sin(math.radians(a.angle))
    along = rel.x() * ux + rel.y() * uy
    perp = QPointF(rel.x() - ux * along, rel.y() - uy * along)
    spacing = math.hypot(perp.x(), perp.y())
    if spacing < MIN_SPACING:
        raise PatternError("两条股道几乎重合，请选择间距更大的股道")
    return Frame(
        origin=QPointF(a.origin),
        u_angle=a.angle,
        v_angle=geometry.angle_of(QPointF(0.0, 0.0), perp),
        spacing=spacing,
        b_angle=b.angle,
    )


def grip(frame: Frame, cursor: QPointF) -> tuple[float, int]:
    """由鼠标位置推出 (沿第一条股道的位置 t, 生成方向 lean)。

    鼠标靠近 A 一侧时向前生成，越过中线则反向生成。
    """
    rel = QPointF(cursor.x() - frame.origin.x(), cursor.y() - frame.origin.y())
    ux, uy = math.cos(math.radians(frame.u_angle)), math.sin(math.radians(frame.u_angle))
    vx, vy = math.cos(math.radians(frame.v_angle)), math.sin(math.radians(frame.v_angle))
    t = rel.x() * ux + rel.y() * uy
    v = rel.x() * vx + rel.y() * vy
    return t, 1 if abs(v) < frame.spacing / 2.0 else -1


# ---------------- 图元字典 ----------------
def _element(type_id: str, pos: QPointF, rotation: float, **props) -> dict:
    data = {
        "type": type_id,
        "x": round(pos.x(), 3),
        "y": round(pos.y(), 3),
        "rotation": round(rotation, 3),
    }
    data.update(props)
    return data


def _switch_params(h: float) -> tuple[float, float]:
    """横向位移 h → (分支角 θ, 直股长度 L)，满足 L·tanθ = h。

    优先取 45°（示例图的紧凑画法）；长度受图元上下限约束，横向很小时角度自动变小。
    """
    if h <= 1e-6:
        raise PatternError("两条股道间距过小")
    length = max(turnout.MIN_LENGTH, min(turnout.MAX_LENGTH, h))
    theta = math.degrees(math.atan2(h, length))
    return max(turnout.MIN_ANGLE, min(turnout.MAX_ANGLE, theta)), length


def _straight_rotation(track_angle: float, direction: float) -> float:
    """直股只能沿股道：在 track_angle 与 +180 里挑更贴近 direction 的那个。"""
    if abs(geometry.signed_angle_diff(track_angle, direction)) <= 90.0:
        return geometry.normalize_angle(track_angle)
    return geometry.normalize_angle(track_angle + 180.0)


def _turnout(
    origin: QPointF,
    track_angle: float,
    target: QPointF,
    length: float,
    paint: LinePaint = LinePaint(),
    style: PatternStyle = PatternStyle(),
) -> dict:
    """在 origin 处放道岔，使曲股端口正好落在 target 上。"""
    direction = geometry.angle_of(origin, target)
    rotation = _straight_rotation(track_angle, direction)
    local = geometry.signed_angle_diff(direction, rotation)
    side = 1.0 if local >= 0.0 else -1.0
    props: dict = {
        "kind": TURNOUT_KIND,
        "length": length,
        "branch_angle": abs(local),
        "mirror": side != turnout.base_side(TURNOUT_KIND),
    }
    if paint.width > 0.0:
        props["line_width"] = paint.width
    if paint.color:
        props["color"] = paint.color
    if style.branch_width > 0.0 and (paint.width <= 0.0 or abs(style.branch_width - paint.width) > 1e-6):
        props["branch_width"] = style.branch_width
        props["taper_length"] = style.taper_length
    return _element("turnout", origin, rotation, **props)


def _segment(start: QPointF, angle: float, length: float, paint: LinePaint = LinePaint()) -> dict:
    props: dict = {"length": length}
    if paint.width > 0.0:
        props["line_width"] = paint.width
    if paint.color:
        props["color"] = paint.color
    return _element("segment", start, angle, **props)


def _island_platform(
    frame: Frame,
    t: float,
    lean: int,
    track_length: float,
    paint_a: LinePaint = LinePaint(),
    paint_b: LinePaint = LinePaint(),
    style: PatternStyle = PatternStyle(),
) -> list[dict]:
    """岛式站台：两条股道正中间放置站台，两侧各留默认间隔（见 core.platform，取自 example5）。

    站台沿股道方向居中在光标处，长度取所选股道的一半（生成后仍可用手柄调整）。
    """
    metrics = platform.island_metrics(frame.spacing, paint_a.width, paint_b.width)
    if not platform.fits_island(metrics):
        raise PatternError("两条股道间距太小，放不下留出标准间隔的站台")
    length = max(platform.PLATFORM_MIN_LENGTH, platform.PLATFORM_LENGTH_RATIO * track_length)
    direction = 1 if lean >= 0 else -1
    angle = frame.u_angle if direction > 0 else geometry.normalize_angle(frame.u_angle + 180.0)
    start = frame.point(t - direction * length / 2.0, metrics.center)
    props: dict = {
        "length": round(length, 3),
        "width": round(metrics.width, 3),
        "kind": "岛式",
    }
    if style.platform_fill:
        props["fill_color"] = style.platform_fill
    if style.platform_fill2:
        props["fill_color2"] = style.platform_fill2
    if style.platform_line:
        props["line_color"] = style.platform_line
    if style.platform_text:
        props["text_color"] = style.platform_text
    return [_element("platform", start, angle, **props)]


def _buffer_stop(pos: QPointF, rotation: float) -> dict:
    return _element("buffer_stop", pos, rotation, width=BUFFER_WIDTH)


# ---------------- 各类组合 ----------------
def _crossover(
    frame: Frame,
    t: float,
    lean: int,
    double: bool,
    paint_a: LinePaint = LinePaint(),
    paint_b: LinePaint = LinePaint(),
    style: PatternStyle = PatternStyle(),
) -> list[dict]:
    """渡线：两个道岔的曲股在两条股道中间对顶，形成 Z 形斜线。

    double=True 时补上另外两个角上的道岔，两条斜线在正中交叉成剪刀渡线。
    """
    d = frame.spacing
    _theta, length = _switch_params(d / 2.0)
    span = 2.0 * length
    center = frame.point(t + lean * length, d / 2.0)
    corners = [
        (frame.point(t, 0.0), frame.u_angle, paint_a),
        (frame.point(t + lean * span, d), frame.b_angle, paint_b),
    ]
    if double:
        corners += [
            (frame.point(t, d), frame.b_angle, paint_b),
            (frame.point(t + lean * span, 0.0), frame.u_angle, paint_a),
        ]
    return [_turnout(origin, angle, center, length, paint, style) for origin, angle, paint in corners]


def _siding(
    frame: Frame,
    t: float,
    lean: int,
    track_length: float,
    paint_a: LinePaint = LinePaint(),
    paint_b: LinePaint = LinePaint(),
    style: PatternStyle = PatternStyle(),
) -> list[dict]:
    """存车线：两条股道正中间生成本股道一半左右长的新线，两端各与上下股道相连。"""
    d = frame.spacing
    v = d / 2.0
    _theta, length = _switch_params(v)
    new_length = max(NEW_LINE_RATIO * track_length, 2.0 * length)
    u_start = t
    u_end = t + lean * new_length
    angle = frame.u_angle if lean > 0 else geometry.normalize_angle(frame.u_angle + 180.0)
    new_paint = LinePaint(style.new_line_width, style.new_line_color or paint_a.color)

    items = [_segment(frame.point(u_start, v), angle, new_length, new_paint)]
    for outer_v, track_angle, paint in ((0.0, frame.u_angle, paint_a), (d, frame.b_angle, paint_b)):
        # 新线两端各用一个道岔从外侧股道接进来
        items.append(
            _turnout(
                frame.point(u_start - lean * length, outer_v),
                track_angle,
                frame.point(u_start, v),
                length,
                paint,
                style,
            )
        )
        items.append(
            _turnout(
                frame.point(u_end + lean * length, outer_v),
                track_angle,
                frame.point(u_end, v),
                length,
                paint,
                style,
            )
        )
    return items


def _turnback(
    frame: Frame,
    t: float,
    lean: int,
    track_length: float,
    paint_a: LinePaint = LinePaint(),
    paint_b: LinePaint = LinePaint(),
    style: PatternStyle = PatternStyle(),
) -> list[dict]:
    """折返线：中间两条新线，两端各自接回相邻股道，两线之间加交叉渡线；一端加车挡。

    对应示例图：两条新线的近端略微出头并以车挡收尾，远端用交叉渡线连通以便折返。
    """
    d = frame.spacing
    inner = d / 3.0
    _theta, length = _switch_params(inner)
    _theta_s, length_s = _switch_params(inner / 2.0)
    scissors_span = 2.0 * length_s
    margin = length  # 近端出头长度，车挡放在这里
    new_length = max(NEW_LINE_RATIO * track_length, scissors_span + 2.0 * margin)
    u_start = t
    u_end = t + lean * new_length
    angle = frame.u_angle if lean > 0 else geometry.normalize_angle(frame.u_angle + 180.0)
    new_paint = LinePaint(style.new_line_width, style.new_line_color or paint_a.color)

    items: list[dict] = []
    pairs = ((inner, 0.0, frame.u_angle, paint_a), (2.0 * inner, d, frame.b_angle, paint_b))
    for v, outer_v, track_angle, paint in pairs:
        tail = frame.point(u_start - lean * margin, v)
        items.append(_segment(tail, angle, new_length + margin, new_paint))
        items.append(_buffer_stop(tail, geometry.normalize_angle(angle + 180.0)))
        items.append(
            _turnout(
                frame.point(u_start - lean * length, outer_v),
                track_angle,
                frame.point(u_start, v),
                length,
                paint,
                style,
            )
        )
        items.append(
            _turnout(
                frame.point(u_end + lean * length, outer_v),
                track_angle,
                frame.point(u_end, v),
                length,
                paint,
                style,
            )
        )

    inner_frame = Frame(
        origin=frame.point(0.0, inner),
        u_angle=frame.u_angle,
        v_angle=frame.v_angle,
        spacing=inner,
        b_angle=frame.b_angle,
    )
    # 新线之间是站线↔站线，不需要再变细
    return items + _crossover(inner_frame, u_end - lean * scissors_span, lean, True, new_paint, new_paint, PatternStyle())


def build(kind: str, a: Track, b: Track, t: float = 0.0, lean: int = 1, style: PatternStyle = PatternStyle()) -> list[dict]:
    """生成组合图元字典。

    kind 取 PATTERN_IDS 之一；t 为沿第一条股道的位置，lean=1/-1 决定生成方向。
    style 用于“区分正线”：把它传给变细的渡线/新线，并在接轨处平滑过渡。
    """
    if kind not in PATTERN_IDS:
        raise PatternError(f"未知的配线类型：{kind}")
    frame = make_frame(a, b)
    direction = 1 if lean >= 0 else -1
    paint_a = LinePaint(a.width, a.color)
    paint_b = LinePaint(b.width, b.color)
    if kind == "crossover_single":
        return _crossover(frame, t, direction, False, paint_a, paint_b, style)
    if kind == "crossover_double":
        return _crossover(frame, t, direction, True, paint_a, paint_b, style)
    if kind == "siding":
        return _siding(frame, t, direction, a.length, paint_a, paint_b, style)
    if kind == "island_platform":
        return _island_platform(frame, t, direction, a.length, paint_a, paint_b, style)
    return _turnback(frame, t, direction, a.length, paint_a, paint_b, style)
