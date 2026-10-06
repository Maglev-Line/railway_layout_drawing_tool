"""工程文件测试：往返一致性、坏文件与版本校验。"""
from __future__ import annotations

import json

import pytest

from core import registry, serialize
from core.model import Document
from graphics.scene import LayoutScene

TYPE_IDS = ("segment", "turnout", "platform", "buffer_stop", "section_marker", "text")


def _build_scene(document: Document) -> LayoutScene:
    scene = LayoutScene(document)
    for order, type_id in enumerate(TYPE_IDS):
        item = registry.create_default(type_id)
        item.setPos(order * 20.0, order * 8.0)
        item.setRotation(order * 15.0)
        scene.addItem(item)
    return scene


def test_roundtrip(tmp_path, qapp):
    document = Document()
    document.title = "测试站"
    document.station = "测试"
    document.grid_size = 20.0
    document.angle_step = 45.0
    document.paper.size_key = "A4"
    document.paper.landscape = False
    scene = _build_scene(document)
    path = tmp_path / "sample.rld"

    serialize.save_project(str(path), document, scene)
    data = serialize.load_project(str(path))

    assert data["format"] == serialize.FORMAT_NAME
    assert data["version"] == serialize.FORMAT_VERSION
    assert data["document"]["title"] == "测试站"
    assert data["document"]["grid_size"] == pytest.approx(20.0)
    assert data["document"]["paper"]["size_key"] == "A4"
    assert data["document"]["paper"]["landscape"] is False

    original = [item.to_dict() for item in scene.layout_items()]
    rebuilt = serialize.build_items(data)
    assert len(rebuilt) == len(original)
    assert [item.to_dict() for item in rebuilt] == original


def test_roundtrip_preserves_tuning(tmp_path, qapp):
    document = Document()
    scene = LayoutScene(document)
    turnout = registry.create_default("turnout")
    turnout.set_prop("kind", "double_slip")
    turnout.set_prop("branch_angle", 25.0)
    turnout.set_prop("label", "1#")
    platform = registry.create_default("platform")
    platform.set_prop("name", "基本站台")
    platform.set_prop("number", "1")
    marker = registry.create_default("section_marker")
    marker.set_prop("style", "隧道")
    marker.set_prop("filled", False)
    for item in (turnout, platform, marker):
        scene.addItem(item)

    path = tmp_path / "tuned.rld"
    serialize.save_project(str(path), document, scene)
    data = serialize.load_project(str(path))
    rebuilt = {item.TYPE_ID: item for item in serialize.build_items(data)}

    assert rebuilt["turnout"].get_prop("kind") == "double_slip"
    assert rebuilt["turnout"].get_prop("branch_angle") == pytest.approx(25.0)
    assert rebuilt["turnout"].get_prop("label") == "1#"
    assert rebuilt["platform"].get_prop("name") == "基本站台"
    assert rebuilt["section_marker"].get_prop("style") == "隧道"
    assert rebuilt["section_marker"].get_prop("filled") is False


def test_load_errors(tmp_path, qapp):
    with pytest.raises(serialize.ProjectFileError):
        serialize.load_project(str(tmp_path / "not_there.rld"))

    broken = tmp_path / "broken.rld"
    broken.write_text("{ 这不是 JSON", encoding="utf-8")
    with pytest.raises(serialize.ProjectFileError):
        serialize.load_project(str(broken))

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    with pytest.raises(serialize.ProjectFileError):
        serialize.load_project(str(other))

    newer = tmp_path / "newer.rld"
    newer.write_text(json.dumps({"format": serialize.FORMAT_NAME, "version": 99}), encoding="utf-8")
    with pytest.raises(serialize.ProjectFileError):
        serialize.load_project(str(newer))


def test_unknown_element_type(tmp_path, qapp):
    path = tmp_path / "bad_element.rld"
    path.write_text(
        json.dumps({"format": serialize.FORMAT_NAME, "version": 1, "elements": [{"type": "ufo"}]}),
        encoding="utf-8",
    )
    data = serialize.load_project(str(path))
    with pytest.raises(serialize.ProjectFileError):
        serialize.build_items(data)


def test_create_element_keeps_id(qapp):
    item = registry.create_default("turnout")
    payload = item.to_dict()
    rebuilt = registry.create_element(payload)
    assert rebuilt.uid == item.uid
    assert rebuilt.to_dict() == payload


def test_registry_covers_all_types(qapp):
    assert {info.type_id for info in registry.all_types()} == set(TYPE_IDS)
    for type_id in TYPE_IDS:
        item = registry.create_default(type_id)
        assert item.TYPE_ID == type_id
        assert item.property_schema()
