"""道岔几何：按类型在局部坐标下生成端口与绘图路径（纯计算，便于测试）。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QTransform

from core import geometry
from core.geometry import LocalPort

KIND_LABELS: tuple[tuple[str, str], ...] = (
    ("single_right", "单开道岔（右开）"),
    ("single_left", "单开道岔（左开）"),
    ("symmetric", "对称道岔（双开）"),
    ("three_right", "三开道岔（右三开）"),
    ("three_left", "三开道岔（左三开）"),
    ("single_slip", "单式交分道岔"),
    ("double_slip", "复式交分道岔"),
)
KIND_IDS = tuple(kind for kind, _ in KIND_LABELS)
KIND_NAMES = dict(KIND_LABELS)
SLIP_KINDS = ("single_slip", "double_slip")
DEFAULT_ANGLE = {
    "single_right": 15.0,
    "single_left": 15.0,
    "symmetric": 15.0,
    "three_right": 15.0,
    "three_left": 15.0,
    "single_slip": 30.0,
    "double_slip": 30.0,
}
MIN_LENGTH = 30.0
MAX_LENGTH = 600.0
MIN_ANGLE = 3.0
MAX_ANGLE = 60.0


@dataclass(frozen=True)
class TurnoutGeometry:
    path: QPainterPath  # 全部线（导出/命中用）
    ports: tuple[LocalPort, ...]
    label_offset: QPointF
    main_path: QPainterPath  # 直股（正线部分）
    branch_path: QPainterPath  # 曲股/交分侧（可单独做变宽过渡）


def is_slip(kind: str) -> bool:
    return kind in SLIP_KINDS


def default_angle(kind: str) -> float:
    return DEFAULT_ANGLE.get(kind, 15.0)


def clamp_length(length: float) -> float:
    return max(MIN_LENGTH, min(MAX_LENGTH, float(length)))


def base_side(kind: str) -> float:
    """mirror=False 时曲股所在侧：+1 为局部 +Y，-1 为局部 -Y。"""
    return -1.0 if kind.endswith("_left") else 1.0


def center_offset(kind: str, length: float) -> float:
    """沿直股从尖轨端到道岔中心的距离：放置时用它把道岔居中在股道上。"""
    if kind in SLIP_KINDS:
        return 0.0
    return clamp_length(length) / 2.0


def clamp_angle(kind: str, angle_deg: float) -> float:
    return max(MIN_ANGLE, min(MAX_ANGLE, float(angle_deg)))


def _curve(p0: QPointF, p3: QPointF, start_deg: float, end_deg: float, k: float) -> QPainterPath:
    """三次贝塞尔：起点切向 start_deg，终点切向 end_deg。"""
    c1 = geometry.point_from(p0, start_deg, k)
    c2 = geometry.point_from(p3, end_deg + 180.0, k)
    path = QPainterPath(p0)
    path.cubicTo(c1, c2, p3)
    return path


def build_geometry(kind: str, length: float, angle_deg: float, mirror: bool = False) -> TurnoutGeometry:
    """生成局部坐标几何：直股沿 +X，原点在道岔起点（尖轨端）。

    main_path 为直股（正线）部分，branch_path 为曲股/交分侧，二者合起来等于 path。
    """
    length = clamp_length(length)
    theta = math.radians(clamp_angle(kind, angle_deg))
    main_path = QPainterPath()
    branch_path = QPainterPath()
    ports: list[LocalPort] = []

    if kind in SLIP_KINDS:
        half = length / 2.0
        side = -1.0 if mirror else 1.0
        dir2 = QPointF(math.cos(theta), side * math.sin(theta))
        ang2 = math.degrees(math.atan2(dir2.y(), dir2.x()))
        west = QPointF(-half, 0.0)
        east = QPointF(half, 0.0)
        south = QPointF(-half * dir2.x(), -half * dir2.y())
        north = QPointF(half * dir2.x(), half * dir2.y())

        main_path.moveTo(west)
        main_path.lineTo(east)
        branch_path.moveTo(south)
        branch_path.lineTo(north)

        a = half
        # 全线圆弧过渡：在臂端相切，中间向外鼓成梭形（复式交分再镜像一条）
        link = _curve(QPointF(-a, 0.0), QPointF(a * dir2.x(), a * dir2.y()), 0.0, ang2, a * 0.85)
        branch_path.addPath(link)
        if kind == "double_slip":
            branch_path.addPath(QTransform().rotate(180.0).map(link))

        ports = [
            LocalPort("西端", west, 180.0, "arm"),
            LocalPort("东端", east, 0.0, "arm"),
            LocalPort("北端", north, ang2, "arm"),
            LocalPort("南端", south, ang2 + 180.0, "arm"),
        ]
        label_offset = QPointF(length * 0.08, -half * abs(math.sin(theta)) - 20.0)

    elif kind == "symmetric":
        side = -1.0 if mirror else 1.0
        ports.append(LocalPort("主干端", QPointF(0.0, 0.0), 180.0, "stem"))
        names = ("曲股终端（上）", "曲股终端（下）")
        for index, sign in enumerate((1.0, -1.0)):
            sign *= side
            end = QPointF(length, sign * length * math.tan(theta))
            branch_path.addPath(_curve(QPointF(0.0, 0.0), end, 0.0, sign * math.degrees(theta), length * 0.45))
            ports.append(LocalPort(names[index], end, sign * math.degrees(theta), "branch"))
        label_offset = QPointF(length * 0.10, -18.0)

    else:  # 单开 / 三开
        side = base_side(kind)
        if mirror:
            side = -side
        straight_end = QPointF(length, 0.0)
        main_path.moveTo(0.0, 0.0)
        main_path.lineTo(straight_end)
        ports.append(LocalPort("直股始端", QPointF(0.0, 0.0), 180.0, "straight"))
        ports.append(LocalPort("直股终端", straight_end, 0.0, "straight"))

        if kind.startswith("three"):
            pairs = ((theta, "曲股终端①"), (2.0 * theta, "曲股终端②"))
        else:
            pairs = ((theta, "曲股终端"),)
        branches: list[QPainterPath] = []
        for angle, name in pairs:
            end = QPointF(length, side * length * math.tan(angle))
            curve = _curve(QPointF(0.0, 0.0), end, 0.0, side * math.degrees(angle), length * 0.45)
            branches.append(curve)
            ports.append(LocalPort(name, end, side * math.degrees(angle), "branch"))
        # 三开道岔的支线要从两条曲线中分离出来：后一条从分岔点起，避免与第一条重叠
        if len(branches) == 1:
            branch_path.addPath(branches[0])
        else:
            branch_path.addPath(branches[-1])
            branch_path.addPath(branches[0])
        label_offset = QPointF(length * 0.10, -side * 18.0)

    path = QPainterPath(main_path)
    path.addPath(branch_path)
    return TurnoutGeometry(
        path=path,
        ports=tuple(ports),
        label_offset=label_offset,
        main_path=main_path,
        branch_path=branch_path,
    )
