"""纯几何工具：单位换算、吸附、角度与曲线计算（不依赖界面）。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF

# 场景单位约定：1 单位 = 96dpi 下的 1 像素 = 0.2646 mm
UNITS_PER_MM = 96.0 / 25.4

# 纸张预设（纵向，单位 mm）
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
}
PAPER_ORDER = ("A4", "A3", "A2")

# 图元下限，避免尺寸被拖到 0
MIN_SEGMENT_LENGTH = 1.0
MIN_RECT_LENGTH = 8.0
MIN_RECT_WIDTH = 4.0


@dataclass(frozen=True)
class LocalPort:
    """图元局部坐标下的端口定义：位置 + 离开端口的出射方向（度）。"""

    name: str
    pos: QPointF
    angle: float
    role: str = "line"


# ---------------- 单位换算 ----------------
def mm_to_units(mm: float) -> float:
    return mm * UNITS_PER_MM


def units_to_mm(units: float) -> float:
    return units / UNITS_PER_MM


# ---------------- 角度 ----------------
def normalize_angle(deg: float) -> float:
    return deg % 360.0


def signed_angle_diff(target: float, ref: float) -> float:
    """target 相对 ref 的最小有符号差，范围 (-180, 180]。"""
    diff = (target - ref + 180.0) % 360.0 - 180.0
    return 180.0 if diff == -180.0 else diff


def angle_of(p1: QPointF, p2: QPointF) -> float:
    return math.degrees(math.atan2(p2.y() - p1.y(), p2.x() - p1.x()))


def toward_angle(deg: float, ref: float) -> float:
    """在“与 ref 夹角 ≤90°”的一侧取 deg 或 deg+180，让方向朝向参考方向。"""
    return deg if abs(signed_angle_diff(deg, ref)) <= 90.0 else deg + 180.0


def point_from(origin: QPointF, angle_deg: float, dist: float) -> QPointF:
    rad = math.radians(angle_deg)
    return QPointF(origin.x() + dist * math.cos(rad), origin.y() + dist * math.sin(rad))


def snap_angle(deg: float, step: float) -> float:
    """把角度吸附到 step 的整数倍（step<=0 表示不吸附）。"""
    if step <= 0:
        return deg
    return normalize_angle(round(deg / step) * step)


def snap_angle_signed(deg: float, step: float) -> float:
    """有符号角度吸附：不归一化到 0~360，保留正负（用于相对夹角）。"""
    if step <= 0:
        return deg
    return round(deg / step) * step


def rotate_point(p: QPointF, angle_deg: float, origin: QPointF | None = None) -> QPointF:
    rad = math.radians(angle_deg)
    ox = origin.x() if origin is not None else 0.0
    oy = origin.y() if origin is not None else 0.0
    dx, dy = p.x() - ox, p.y() - oy
    return QPointF(
        ox + dx * math.cos(rad) - dy * math.sin(rad),
        oy + dx * math.sin(rad) + dy * math.cos(rad),
    )


# ---------------- 距离与吸附 ----------------
def distance(p1: QPointF, p2: QPointF) -> float:
    return math.hypot(p2.x() - p1.x(), p2.y() - p1.y())


def midpoint(p1: QPointF, p2: QPointF) -> QPointF:
    return QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)


def snap_value(value: float, step: float) -> float:
    if step <= 0:
        return value
    return round(value / step) * step


def snap_point_to_grid(p: QPointF, step: float) -> QPointF:
    return QPointF(snap_value(p.x(), step), snap_value(p.y(), step))


def project_on_direction(anchor: QPointF, point: QPointF, angle_deg: float) -> float:
    """point 在 anchor 出发、方向 angle_deg 的射线上的投影长度。"""
    rad = math.radians(angle_deg)
    return (point.x() - anchor.x()) * math.cos(rad) + (point.y() - anchor.y()) * math.sin(rad)


def closest_point_on_segment(point: QPointF, start: QPointF, end: QPointF) -> QPointF:
    """线段上距 point 最近的点（超出两端时取端点）。"""
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return QPointF(start)
    t = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return QPointF(start.x() + t * dx, start.y() + t * dy)


def distance_to_segment(point: QPointF, start: QPointF, end: QPointF) -> float:
    """点到线段的最近距离。"""
    return distance(point, closest_point_on_segment(point, start, end))


# 交叉断开：空隙半长 = 该倍数 × 被跨越股道的线宽（取自 examples/example6 实测 ≈1.4）
CROSS_GAP_FACTOR = 1.4
MIN_CROSS_ANGLE = 5.0  # 夹角小于该值视为几乎平行，不做交叉断开


def segment_intersection(
    a1: QPointF, a2: QPointF, b1: QPointF, b2: QPointF, min_angle: float = MIN_CROSS_ANGLE
) -> tuple[QPointF, float] | None:
    """两条线段的交点：返回 (交点, 交点在第一条线段上的比例 t∈[0,1])；不相交返回 None。

    夹角小于 min_angle 视为平行/重合，返回 None（避免擦角交叉算出巨长空隙）。
    """
    dx_a, dy_a = a2.x() - a1.x(), a2.y() - a1.y()
    dx_b, dy_b = b2.x() - b1.x(), b2.y() - b1.y()
    denom = dx_a * dy_b - dy_a * dx_b
    if abs(denom) <= 1e-9:
        return None
    cross_angle = abs(math.degrees(math.atan2(denom, dx_a * dx_b + dy_a * dy_b)))
    cross_angle = min(cross_angle, 180.0 - cross_angle)
    if cross_angle < min_angle:
        return None
    t = ((b1.x() - a1.x()) * dy_b - (b1.y() - a1.y()) * dx_b) / denom
    u = ((b1.x() - a1.x()) * dy_a - (b1.y() - a1.y()) * dx_a) / denom
    if not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
        return None
    return QPointF(a1.x() + t * dx_a, a1.y() + t * dy_a), t


# ---------------- 曲线 ----------------
def cubic_point(p0: QPointF, c1: QPointF, c2: QPointF, p3: QPointF, t: float) -> QPointF:
    s = 1.0 - t
    return QPointF(
        s * s * s * p0.x() + 3 * s * s * t * c1.x() + 3 * s * t * t * c2.x() + t * t * t * p3.x(),
        s * s * s * p0.y() + 3 * s * s * t * c1.y() + 3 * s * t * t * c2.y() + t * t * t * p3.y(),
    )


def sample_cubic(p0: QPointF, c1: QPointF, c2: QPointF, p3: QPointF, count: int = 24) -> list[QPointF]:
    count = max(2, count)
    return [cubic_point(p0, c1, c2, p3, i / (count - 1)) for i in range(count)]
