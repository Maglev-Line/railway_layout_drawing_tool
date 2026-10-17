"""站台与股道的排布几何（纯计算，不依赖界面）：默认间隔、岛式站台尺寸与长边吸附。

默认间隔取自 ``examples/example5带站前单渡线的岛式站台.png`` 实测：
股道线宽 ≈ 9.5 px、两条股道中心线间距 ≈ 93.5 px、站台宽 ≈ 67 px，
站台边缘到相邻股道中心线 ≈ 13.25 px ≈ **1.4 倍股道线宽**；
按默认线宽 4.0 单位换算即 **5.6 单位**，就是下面的 ``PLATFORM_TRACK_GAP``。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

DEFAULT_TRACK_WIDTH = 4.0  # 与 ui.theme.TRACK_WIDTH_DEFAULT 一致的默认股道线宽
PLATFORM_TRACK_GAP_RATIO = 1.4  # example5 实测：间隔 / 股道线宽
PLATFORM_TRACK_GAP = round(PLATFORM_TRACK_GAP_RATIO * DEFAULT_TRACK_WIDTH, 2)  # 5.6：股道中心线 → 站台长边
PLATFORM_EDGE_CLEARANCE = 1.5  # 站台长边与股道线边缘之间至少留出的可见间隙
MIN_PLATFORM_WIDTH = 8.0  # 站台宽度下限
PLATFORM_MIN_LENGTH = 60.0  # 自动生成站台的长度下限
PLATFORM_LENGTH_RATIO = 0.5  # 岛式站台长度 = 所选股道长度 × 该比例


def gap_for_track(line_width: float = 0.0) -> float:
    """站台长边应离开该股道中心线的距离：默认间隔，但至少留出可见间隙。"""
    return max(PLATFORM_TRACK_GAP, float(line_width or 0.0) / 2.0 + PLATFORM_EDGE_CLEARANCE)


@dataclass(frozen=True)
class TrackOffset:
    """站台局部坐标下的一条「与长边大致平行」的股道：横向位置 y 与线宽。"""

    y: float
    width: float = DEFAULT_TRACK_WIDTH


@dataclass(frozen=True)
class IslandMetrics:
    """两条股道之间岛式站台的尺寸（v 为沿法向的局部坐标，0 在第一条股道上）。"""

    low: float  # 站台靠第一条股道一侧的长边
    high: float  # 站台靠第二条股道一侧的长边

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def center(self) -> float:
        return (self.low + self.high) / 2.0

    @property
    def gap(self) -> float:
        return self.low


def island_metrics(
    spacing: float, width_a: float = DEFAULT_TRACK_WIDTH, width_b: float = DEFAULT_TRACK_WIDTH
) -> IslandMetrics:
    """两条股道之间居中放置的岛式站台：两侧各留该股道的默认间隔。"""
    return IslandMetrics(low=gap_for_track(width_a), high=float(spacing) - gap_for_track(width_b))


def fits_island(metrics: IslandMetrics) -> bool:
    return metrics.width >= MIN_PLATFORM_WIDTH


def snap_edges(
    edge_a: float,
    edge_b: float,
    tracks: Sequence[TrackOffset],
    tolerance: float,
) -> tuple[float, float, bool, bool]:
    """把站台两条长边吸附到「股道 ± 默认间隔」。

    edge_a / edge_b 为站台两条长边在局部坐标下的横向位置（edge_a < edge_b）。
    返回 (吸附后的 edge_a, 吸附后的 edge_b, 是否吸附了 edge_a, 是否吸附了 edge_b)：
    只有股道位于该长边所属的一侧（相对站台中线）且距离默认间隔不超过 tolerance 时才吸附。
    """
    center = (edge_a + edge_b) / 2.0
    new_a, hit_a = _snap_one(edge_a, tracks, tolerance, upper=True, center=center)
    new_b, hit_b = _snap_one(edge_b, tracks, tolerance, upper=False, center=center)
    if hit_a and hit_b and new_a > new_b - MIN_PLATFORM_WIDTH:
        # 两条股道太近，容不下站台：只保留上侧那一条，避免宽度被压成负值
        return (new_a, edge_b, True, False)
    return new_a, new_b, hit_a, hit_b


def _snap_one(
    edge: float, tracks: Sequence[TrackOffset], tolerance: float, *, upper: bool, center: float
):
    """upper=True 吸附站台上侧长边（候选股道在站台中线以上，长边落在「股道 y + 间隔」）；
    upper=False 吸附下侧长边（候选股道在中线以下，长边落在「股道 y − 间隔」）。"""
    best: tuple[float, float] | None = None
    for track in tracks:
        if (track.y > center) if upper else (track.y < center):
            continue  # 该股道属于站台另一侧
        gap = gap_for_track(track.width)
        target = track.y + gap if upper else track.y - gap
        dist = abs(edge - target)
        if dist <= tolerance and (best is None or dist < best[0]):
            best = (dist, target)
    if best is None:
        return edge, False
    return best[1], True
