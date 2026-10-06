"""PDF 导出：QPdfWriter + scene.render()（矢量输出，自动隐藏网格与选择状态）。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter

from core.model import Document
from graphics.scene import LayoutScene

EXPORT_DPI = 300.0
MM_PER_INCH = 25.4
SCALE_CHOICES = (("fit", "自动适配纸张"), ("exact", "100% 原始尺寸"))
SCOPE_CHOICES = (("content", "整张图"), ("view", "当前视图"))
PAGE_CHOICES = (("A4", "A4"), ("A3", "A3"), ("A2", "A2"), ("custom", "自定义"))
ORIENT_CHOICES = ((True, "横向"), (False, "纵向"))


class ExportError(Exception):
    """导出失败；消息面向用户，包含原因与下一步。"""


@dataclass
class ExportOptions:
    scope: str = "content"
    page_key: str = "A3"
    landscape: bool = True
    custom_width_mm: float = 420.0
    custom_height_mm: float = 297.0
    margin_mm: float = 10.0
    scale_mode: str = "fit"


@dataclass
class ExportPlan:
    source: QRectF
    target: QRectF
    page_px: QSizeF
    fits: bool
    page_size: QPageSize
    title: str = ""


def page_size_mm(options: ExportOptions) -> tuple[float, float]:
    from core import geometry

    if options.page_key in geometry.PAPER_SIZES_MM:
        width, height = geometry.PAPER_SIZES_MM[options.page_key]
    else:
        width, height = options.custom_width_mm, options.custom_height_mm
    if options.landscape:
        width, height = max(width, height), min(width, height)
    else:
        width, height = min(width, height), max(width, height)
    return width, height


def _mm_to_px(mm: float) -> float:
    return mm / MM_PER_INCH * EXPORT_DPI


def plan_export(
    scene: LayoutScene,
    document: Document,
    options: ExportOptions,
    view_rect: QRectF | None = None,
) -> ExportPlan:
    width_mm, height_mm = page_size_mm(options)
    page_px = QSizeF(_mm_to_px(width_mm), _mm_to_px(height_mm))
    margin_px = _mm_to_px(max(0.0, options.margin_mm))
    area = QRectF(
        margin_px,
        margin_px,
        max(1.0, page_px.width() - 2 * margin_px),
        max(1.0, page_px.height() - 2 * margin_px),
    )

    if options.scope == "view" and view_rect is not None and not view_rect.isEmpty():
        source = QRectF(view_rect)
    else:
        source = scene.bounds()
        if source.isNull():
            raise ExportError("图纸上还没有可导出的内容；请先绘制股道、道岔或站台，再导出 PDF。")
    if source.isNull() or source.width() <= 0.0 or source.height() <= 0.0:
        raise ExportError("图纸上还没有可导出的内容；请先绘制股道、道岔或站台，再导出 PDF。")

    if options.scale_mode == "exact":
        factor = EXPORT_DPI / 96.0
    else:
        factor = min(area.width() / source.width(), area.height() / source.height())
    width = source.width() * factor
    height = source.height() * factor
    target = QRectF(
        area.center().x() - width / 2.0,
        area.center().y() - height / 2.0,
        width,
        height,
    )
    fits = width <= area.width() + 0.5 and height <= area.height() + 0.5
    return ExportPlan(
        source=source,
        target=target,
        page_px=page_px,
        fits=fits,
        page_size=QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter, "配线图", QPageSize.SizeMatchPolicy.ExactMatch),
        title=document.title,
    )


def export_pdf(
    path: str,
    scene: LayoutScene,
    document: Document,
    options: ExportOptions,
    view_rect: QRectF | None = None,
) -> ExportPlan:
    plan = plan_export(scene, document, options, view_rect)

    writer = QPdfWriter(path)
    writer.setResolution(int(EXPORT_DPI))
    writer.setPageSize(plan.page_size)
    writer.setTitle(document.title)
    writer.setCreator("铁路配线图绘制器")

    painter = QPainter()
    if not painter.begin(writer):
        raise ExportError("无法写入 PDF 文件；请检查目标目录权限，或换一个文件名后重试。")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        saved_selection = scene.begin_export()
        try:
            scene.render(painter, plan.target, plan.source, Qt.AspectRatioMode.IgnoreAspectRatio)
        finally:
            scene.end_export(saved_selection)
    finally:
        painter.end()
    return plan
