"""站台吸附：把站台长边吸附到「股道中心线 ± 默认间隔」（间隔见 core.platform，取自 example5）。

只在「股道与站台长边大致平行」时生效：此时股道在站台局部坐标下是一条近乎水平的线，
两条长边各自独立吸附到最近的相邻股道；两条边都命中时站台宽度随之间距收缩，
于是岛式站台自动变成「居中、两侧留默认间隔」的样子。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF

from core import geometry, platform
from graphics.items.platform_item import PlatformItem
from graphics.items.segment_item import SegmentItem

ANGLE_TOLERANCE = 12.0  # 与站台长边夹角不超过该值才参与吸附（度）


def track_offsets(item: PlatformItem, scene) -> list[platform.TrackOffset]:
    """站台局部坐标下、与长边大致平行且横向重叠的股道（横向位置 + 线宽）。"""
    if scene is None:
        return []
    length = float(item.get_prop("length"))
    center_x = length / 2.0
    offsets: list[platform.TrackOffset] = []
    for other in scene.layout_items():
        if other is item or not isinstance(other, SegmentItem):
            continue
        if not other.isVisible() or other.opacity() < 0.9:  # 预览幽灵不参与
            continue
        start = item.mapFromScene(other.mapToScene(QPointF(0.0, 0.0)))
        end = item.mapFromScene(other.mapToScene(QPointF(float(other.get_prop("length")), 0.0)))
        if abs(geometry.signed_angle_diff(geometry.angle_of(start, end), 0.0)) > ANGLE_TOLERANCE:
            continue
        span_lo, span_hi = sorted((start.x(), end.x()))
        if span_hi < 0.0 or span_lo > length:
            continue  # 横向不重叠，不算相邻
        if span_hi - span_lo < 1e-6:
            continue
        ratio = max(0.0, min(1.0, (center_x - start.x()) / (span_hi - span_lo)))
        y = start.y() + ratio * (end.y() - start.y())
        offsets.append(platform.TrackOffset(y=y, width=float(other.get_prop("line_width"))))
    return offsets


def snap_platform(item: PlatformItem, scene, tolerance: float) -> bool:
    """按默认间隔吸附站台长边（原地改基准点与宽度）；返回是否真的发生了位移/改宽。"""
    offsets = track_offsets(item, scene)
    if not offsets:
        return False
    width = float(item.get_prop("width"))
    edge_a, edge_b = -width / 2.0, width / 2.0
    new_a, new_b, hit_a, hit_b = platform.snap_edges(edge_a, edge_b, offsets, tolerance)
    if not (hit_a or hit_b):
        return False
    center = (new_a + new_b) / 2.0
    new_width = max(platform.MIN_PLATFORM_WIDTH, new_b - new_a)
    resized = abs(new_width - width) > 1e-6
    if not (resized or abs(center) > 1e-6):
        return False  # 已经在标准位置上，不必重复改动（避免产生空撤销步骤）
    if resized:
        item.set_prop("width", new_width)
    if abs(center) > 1e-6:
        # 站台自身的局部 y=0 就是中线：把基准点沿局部 +y 平移 center 即可
        shift = geometry.point_from(QPointF(0.0, 0.0), item.rotation() + 90.0, center)
        item.setPos(item.pos().x() + shift.x(), item.pos().y() + shift.y())
    return True
