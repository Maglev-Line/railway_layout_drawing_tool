"""几何与吸附数学测试（纯逻辑，不需要 Qt 应用）。"""
from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QPointF

from core import geometry


def test_unit_conversion():
    assert geometry.mm_to_units(25.4) == pytest.approx(96.0)
    assert geometry.units_to_mm(96.0) == pytest.approx(25.4)


def test_snap_value_and_point():
    assert geometry.snap_value(23.0, 10.0) == pytest.approx(20.0)
    assert geometry.snap_value(-6.0, 10.0) == pytest.approx(-10.0)
    assert geometry.snap_value(23.0, 0.0) == pytest.approx(23.0)
    point = geometry.snap_point_to_grid(QPointF(23.0, 47.0), 10.0)
    assert (point.x(), point.y()) == (20.0, 50.0)


def test_snap_angle():
    assert geometry.snap_angle(17.0, 15.0) == pytest.approx(15.0)
    assert geometry.snap_angle(-17.0, 15.0) == pytest.approx(345.0)
    assert geometry.snap_angle(17.0, 0.0) == pytest.approx(17.0)
    # 有符号版本保留正负，便于相对夹角吸附
    assert geometry.snap_angle_signed(-53.0, 15.0) == pytest.approx(-60.0)
    assert geometry.snap_angle_signed(53.0, 15.0) == pytest.approx(60.0)
    assert geometry.snap_angle_signed(-53.0, 0.0) == pytest.approx(-53.0)


def test_angle_of_and_point_from():
    assert geometry.angle_of(QPointF(0.0, 0.0), QPointF(10.0, 0.0)) == pytest.approx(0.0)
    assert geometry.angle_of(QPointF(0.0, 0.0), QPointF(0.0, 10.0)) == pytest.approx(90.0)
    point = geometry.point_from(QPointF(5.0, 5.0), 90.0, 3.0)
    assert point.x() == pytest.approx(5.0)
    assert point.y() == pytest.approx(8.0)


def test_project_and_rotate():
    assert geometry.project_on_direction(QPointF(0.0, 0.0), QPointF(10.0, 4.0), 0.0) == pytest.approx(10.0)
    rotated = geometry.rotate_point(QPointF(10.0, 0.0), 90.0)
    assert rotated.x() == pytest.approx(0.0, abs=1e-9)
    assert rotated.y() == pytest.approx(10.0)


def test_signed_angle_diff():
    assert geometry.signed_angle_diff(10.0, 350.0) == pytest.approx(20.0)
    assert geometry.signed_angle_diff(350.0, 10.0) == pytest.approx(-20.0)
    assert geometry.signed_angle_diff(0.0, 0.0) == pytest.approx(0.0)


def test_toward_angle():
    assert geometry.toward_angle(30.0, 60.0) == pytest.approx(30.0)
    assert geometry.toward_angle(30.0, -120.0) == pytest.approx(210.0)
    assert geometry.toward_angle(0.0, 90.0) == pytest.approx(0.0)


def test_normalize_angle():
    assert geometry.normalize_angle(-90.0) == pytest.approx(270.0)
    assert geometry.normalize_angle(450.0) == pytest.approx(90.0)


def test_distance_and_midpoint():
    assert geometry.distance(QPointF(0.0, 0.0), QPointF(3.0, 4.0)) == pytest.approx(5.0)
    middle = geometry.midpoint(QPointF(0.0, 0.0), QPointF(10.0, 20.0))
    assert (middle.x(), middle.y()) == (5.0, 10.0)


def test_closest_point_and_distance_to_segment():
    start, end = QPointF(0.0, 0.0), QPointF(100.0, 0.0)
    foot = geometry.closest_point_on_segment(QPointF(30.0, 7.0), start, end)
    assert (foot.x(), foot.y()) == (30.0, 0.0)
    assert geometry.distance_to_segment(QPointF(30.0, 7.0), start, end) == pytest.approx(7.0)
    # 超出端点时取端点，零长线段退化为点距离
    assert geometry.closest_point_on_segment(QPointF(300.0, 0.0), start, end) == QPointF(100.0, 0.0)
    assert geometry.distance_to_segment(QPointF(0.0, 4.0), start, start) == pytest.approx(4.0)


def test_sample_cubic_endpoints():
    p0, c1, c2, p3 = QPointF(0, 0), QPointF(1, 0), QPointF(2, 1), QPointF(3, 1)
    points = geometry.sample_cubic(p0, c1, c2, p3, 8)
    assert len(points) == 8
    assert points[0] == p0
    assert points[-1] == p3
    angle = math.degrees(math.atan2(points[3].y() - points[2].y(), points[3].x() - points[2].x()))
    assert -90.0 < angle < 90.0
