"""道岔几何测试：端口数量、位置、出射方向与参数钳制。"""
from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF

from core import turnout


def _port(geometry, name: str):
    for port in geometry.ports:
        if port.name == name:
            return port
    raise AssertionError(f"缺少端口：{name}")


def test_single_turnout_ports():
    geometry = turnout.build_geometry("single_right", 120.0, 15.0, False)
    assert len(geometry.ports) == 3
    start = _port(geometry, "直股始端")
    end = _port(geometry, "直股终端")
    branch = _port(geometry, "曲股终端")
    assert start.pos.x() == pytest.approx(0.0)
    assert start.pos.y() == pytest.approx(0.0)
    assert start.angle == pytest.approx(180.0)
    assert end.pos.x() == pytest.approx(120.0)
    assert end.pos.y() == pytest.approx(0.0)
    assert end.angle == pytest.approx(0.0)
    assert branch.pos.x() == pytest.approx(120.0)
    assert branch.pos.y() == pytest.approx(120.0 * math.tan(math.radians(15.0)))
    assert branch.angle == pytest.approx(15.0)


def test_left_turnout_is_mirrored():
    right = turnout.build_geometry("single_right", 120.0, 15.0, False)
    left = turnout.build_geometry("single_left", 120.0, 15.0, False)
    assert _port(right, "曲股终端").pos.y() == pytest.approx(-_port(left, "曲股终端").pos.y())
    mirrored = turnout.build_geometry("single_right", 120.0, 15.0, True)
    assert _port(mirrored, "曲股终端").pos.y() == pytest.approx(-_port(right, "曲股终端").pos.y())


def test_symmetric_turnout_ports():
    geometry = turnout.build_geometry("symmetric", 100.0, 20.0, False)
    assert len(geometry.ports) == 3
    names = [port.name for port in geometry.ports]
    assert "主干端" in names
    upper = _port(geometry, "曲股终端（上）")
    lower = _port(geometry, "曲股终端（下）")
    assert upper.pos.y() == pytest.approx(-lower.pos.y())
    assert upper.angle == pytest.approx(20.0)
    assert lower.angle == pytest.approx(-20.0)


def test_three_way_turnout_ports():
    geometry = turnout.build_geometry("three_right", 150.0, 15.0, False)
    assert len(geometry.ports) == 4
    first = _port(geometry, "曲股终端①")
    second = _port(geometry, "曲股终端②")
    assert second.pos.y() > first.pos.y() > 0.0
    assert second.angle == pytest.approx(30.0)


def test_slip_ports_and_links():
    single = turnout.build_geometry("single_slip", 160.0, 30.0, False)
    double = turnout.build_geometry("double_slip", 160.0, 30.0, False)
    assert len(single.ports) == 4
    assert len(double.ports) == 4
    west = _port(single, "西端")
    east = _port(single, "东端")
    north = _port(single, "北端")
    south = _port(single, "南端")
    assert west.pos.x() == pytest.approx(-80.0)
    assert east.pos.x() == pytest.approx(80.0)
    assert north.pos.y() == pytest.approx(80.0 * math.sin(math.radians(30.0)))
    assert south.pos.y() == pytest.approx(-north.pos.y())
    assert north.angle == pytest.approx(30.0)
    assert south.angle == pytest.approx(210.0)
    # 复式交分比单式多一条连接曲线
    assert double.path.length() > single.path.length()


def test_bounds_contain_all_ports():
    for kind in turnout.KIND_IDS:
        geometry = turnout.build_geometry(kind, 140.0, 15.0, False)
        bounds = geometry.path.boundingRect()
        for port in geometry.ports:
            assert bounds.adjusted(-1.0, -1.0, 1.0, 1.0).contains(port.pos), (kind, port.name)


def test_parameter_clamping():
    tiny = turnout.build_geometry("single_right", 1.0, 1.0, False)
    huge = turnout.build_geometry("single_right", 100000.0, 89.0, False)
    assert _port(tiny, "直股终端").pos.x() == pytest.approx(turnout.MIN_LENGTH)
    assert _port(tiny, "曲股终端").angle == pytest.approx(turnout.MIN_ANGLE)
    assert _port(huge, "直股终端").pos.x() == pytest.approx(turnout.MAX_LENGTH)
    assert _port(huge, "曲股终端").angle == pytest.approx(turnout.MAX_ANGLE)


def test_defaults_and_labels():
    assert set(turnout.DEFAULT_ANGLE) == set(turnout.KIND_IDS)
    assert turnout.default_angle("double_slip") == pytest.approx(30.0)
    assert turnout.is_slip("single_slip") and not turnout.is_slip("turnout")
    assert turnout.KIND_NAMES["symmetric"] == "对称道岔（双开）"


def test_base_side_and_center_offset():
    assert turnout.base_side("single_right") == pytest.approx(1.0)
    assert turnout.base_side("single_left") == pytest.approx(-1.0)
    assert turnout.base_side("three_left") == pytest.approx(-1.0)
    # 单开/对称/三开的中心在直股中点；交分道岔原点即中心
    assert turnout.center_offset("single_right", 120.0) == pytest.approx(60.0)
    assert turnout.center_offset("symmetric", 100.0) == pytest.approx(50.0)
    assert turnout.center_offset("double_slip", 160.0) == pytest.approx(0.0)
    # 长度参与钳制，避免越界
    assert turnout.center_offset("single_right", 1.0) == pytest.approx(turnout.MIN_LENGTH / 2.0)
