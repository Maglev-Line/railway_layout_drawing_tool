"""渲染与导出测试：确保图元绘制代码可运行、PDF 可生成。"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QImage, QPainter

from core import pdf_export, registry
from core.model import Document
from core.pdf_export import ExportOptions
from graphics.scene import LayoutScene

TYPE_IDS = ("segment", "turnout", "platform", "buffer_stop", "section_marker", "text")


def _populate(document: Document) -> LayoutScene:
    scene = LayoutScene(document)
    for order, type_id in enumerate(TYPE_IDS):
        item = registry.create_default(type_id)
        item.setPos(order * 80.0, 60.0 + order * 30.0)
        item.setRotation(order * 10.0)
        scene.addItem(item)
    return scene


def test_render_scene_to_image(qapp):
    document = Document()
    scene = _populate(document)
    source = scene.bounds()
    assert not source.isNull()

    image = QImage(QSize(1000, 700), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0xFFFFFFFF)
    painter = QPainter(image)
    try:
        scene.render(painter, QRectF(image.rect()), source)
    finally:
        painter.end()
    assert image.size() == QSize(1000, 700)


def test_export_pdf_creates_file(qapp, tmp_path):
    document = Document()
    scene = _populate(document)
    path = tmp_path / "out.pdf"
    plan = pdf_export.export_pdf(str(path), scene, document, ExportOptions(page_key="A4"))
    assert plan.fits
    assert path.exists()
    assert path.stat().st_size > 1000
    assert scene.export_mode is False
    assert path.read_bytes()[:5] == b"%PDF-"


def test_export_exact_scale_reports_overflow(qapp, tmp_path):
    document = Document()
    scene = LayoutScene(document)
    long_segment = registry.create_default("segment")
    long_segment.set_prop("length", 4000.0)
    scene.addItem(long_segment)

    options = ExportOptions(page_key="A4", scale_mode="exact")
    plan = pdf_export.plan_export(scene, document, options)
    assert plan.fits is False

    fit_plan = pdf_export.plan_export(scene, document, ExportOptions(page_key="A4", scale_mode="fit"))
    assert fit_plan.fits is True


def test_export_empty_scene_raises(qapp):
    document = Document()
    scene = LayoutScene(document)
    with pytest.raises(pdf_export.ExportError):
        pdf_export.plan_export(scene, document, ExportOptions())


def test_page_size_orientation():
    portrait = pdf_export.page_size_mm(ExportOptions(page_key="A3", landscape=False))
    landscape = pdf_export.page_size_mm(ExportOptions(page_key="A3", landscape=True))
    assert portrait == (297.0, 420.0)
    assert landscape == (420.0, 297.0)
    custom = pdf_export.page_size_mm(ExportOptions(page_key="custom", landscape=False, custom_width_mm=200.0, custom_height_mm=500.0))
    assert custom == (200.0, 500.0)
