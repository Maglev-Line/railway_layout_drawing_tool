"""画布工具：选择、股道拉线、元素放置、道岔子类型与配线组合生成。"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtWidgets import QGraphicsItem

from core import geometry, patterns, registry, turnout
from core.commands import AddItemsCommand, EditPropertiesCommand
from graphics import style
from graphics.items.base import LayoutItem
from graphics.items.buffer_stop_item import BufferStopItem
from graphics.items.connector_item import ConnectorItem
from graphics.items.platform_item import PlatformItem
from graphics.items.section_marker_item import SectionMarkerItem
from graphics.items.segment_item import SegmentItem
from graphics.items.text_item import TextItem
from graphics.items.turnout_item import TurnoutItem
from graphics.scene import SnapResult
from graphics.snap_platform import snap_platform

SNAP_PX = 12.0  # 端口吸附阈值（屏幕像素）
HANDLE_PX = 7.0  # 手柄拾取半径（屏幕像素）
MIN_DRAG_PX = 5.0  # 拖拽判定阈值（屏幕像素）
PICK_PX = 18.0  # 组合工具点选股道的宽松判定半径（屏幕像素）
GHOST_OPACITY = 0.45
MIN_ITEM_GAP = 1.0
CONNECTOR_MIN_CROSS_ANGLE = 10.0  # 两条股道的夹角小于该值不算交叉
CONNECTOR_MIN_OFFSET = 2.0  # 接点离交叉点的最小距离（单位）

GROUP_BASIC = "绘制元素"
GROUP_TURNOUT = "道岔"
GROUP_PATTERN = "组合配线"
GROUP_CONNECTOR = "联络线"
TOOL_GROUPS: tuple[str, ...] = (GROUP_BASIC, GROUP_TURNOUT, GROUP_PATTERN, GROUP_CONNECTOR)

TURNOUT_HINT = "两步放置：先点主线位置，再拖出曲股方向（右键/Esc 退回上一步）"
PATTERN_HINT = "依次点两条股道 → 移动鼠标选方向 → 再点一次生成（右键/Esc 退回上一步）"
ISLAND_HINT = "依次点两条平行股道 → 移动鼠标定位置 → 再点一次在中间生成站台（两侧自动留默认间隔）"
CONNECTOR_HINT = "依次点两条交叉的股道 → 移动鼠标定两个接点 → 再点一次生成（右键/Esc 退回上一步）"


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    name: str
    cls: type | None
    shortcut: str
    hint: str = ""
    group: str = GROUP_BASIC
    preset: dict | None = None  # 新建图元的初始属性


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("select", "选择", None, "V", "点选 / 框选 / 拖动元素与手柄"),
    ToolSpec("segment", "股道线段", SegmentItem, "L", "按下拖拽或两次点击画线，可连续绘制"),
    ToolSpec("platform", "站台", PlatformItem, "P", "拖出矩形范围"),
    ToolSpec("buffer_stop", "车挡", BufferStopItem, "B", "点击放在股道末端"),
    ToolSpec("section_marker", "区间标记", SectionMarkerItem, "M", "沿方向拖拽出长度"),
    ToolSpec("text", "文字标注", TextItem, "X", "点击放置后在右侧改内容"),
    ToolSpec("turnout_single", "单开道岔", TurnoutItem, "T", TURNOUT_HINT, GROUP_TURNOUT, {"kind": "single_right"}),
    ToolSpec("turnout_symmetric", "双开道岔", TurnoutItem, "", TURNOUT_HINT, GROUP_TURNOUT, {"kind": "symmetric"}),
    ToolSpec("turnout_three", "三开道岔", TurnoutItem, "", TURNOUT_HINT, GROUP_TURNOUT, {"kind": "three_right"}),
    ToolSpec("turnout_slip", "单式交分", TurnoutItem, "", TURNOUT_HINT, GROUP_TURNOUT, {"kind": "single_slip"}),
    ToolSpec(
        "turnout_double_slip", "复式交分", TurnoutItem, "", TURNOUT_HINT, GROUP_TURNOUT, {"kind": "double_slip"}
    ),
    ToolSpec("crossover_single", "单渡线", None, "", PATTERN_HINT, GROUP_PATTERN),
    ToolSpec("crossover_double", "交叉渡线", None, "", PATTERN_HINT, GROUP_PATTERN),
    ToolSpec("siding", "存车线", None, "", PATTERN_HINT, GROUP_PATTERN),
    ToolSpec("turnback", "折返线", None, "", PATTERN_HINT, GROUP_PATTERN),
    ToolSpec("island_platform", "岛式站台", None, "", ISLAND_HINT, GROUP_PATTERN),
    ToolSpec(
        "connector_straight", "联络线（直线）", ConnectorItem, "", CONNECTOR_HINT, GROUP_CONNECTOR,
        {"kind": "直线"},
    ),
    ToolSpec(
        "connector_curve", "联络线（曲线）", ConnectorItem, "", CONNECTOR_HINT, GROUP_CONNECTOR,
        {"kind": "曲线"},
    ),
)
TOOL_SPEC_MAP = {spec.tool_id: spec for spec in TOOL_SPECS}
PATTERN_TOOL_IDS = tuple(spec.tool_id for spec in TOOL_SPECS if spec.group == GROUP_PATTERN)
CONNECTOR_TOOL_IDS = tuple(spec.tool_id for spec in TOOL_SPECS if spec.group == GROUP_CONNECTOR)


def nearest_segment(
    scene, pos: QPointF, threshold: float, exclude=()
) -> tuple[LayoutItem, float, QPointF] | None:
    """光标附近的股道线段：返回 (图元, 方向角, 中线垂足)；超出阈值返回 None。"""
    excluded = set(exclude)
    best: tuple[float, LayoutItem, float, QPointF] | None = None
    for item in scene.layout_items():
        if not isinstance(item, SegmentItem) or item in excluded or not item.isVisible():
            continue
        start = item.mapToScene(QPointF(0.0, 0.0))
        end = item.mapToScene(QPointF(float(item.get_prop("length")), 0.0))
        foot = geometry.closest_point_on_segment(pos, start, end)
        dist = geometry.distance(pos, foot)
        if dist <= threshold and (best is None or dist < best[0]):
            best = (dist, item, geometry.angle_of(start, end), foot)
    if best is None:
        return None
    return best[1], best[2], best[3]


def track_of(item: LayoutItem) -> patterns.Track:
    """把股道线段图元转成组合生成用的抽象股道（含自身线宽/颜色）。"""
    return patterns.Track(
        QPointF(item.pos()),
        item.rotation(),
        float(item.get_prop("length")),
        width=float(item.get_prop("line_width")),
        color=str(item.get_prop("color")),
    )


def pattern_style() -> patterns.PatternStyle:
    """按“区分正线”设置生成组合的线型：关闭时与所选股道一致（不变细）。

    站台配色也随默认样式走，保证「岛式站台」与手绘站台观感一致。
    """
    current = style.current()
    platform_colors = {
        "platform_fill": current.platform_fill,
        "platform_fill2": current.platform_fill2,
        "platform_line": current.platform_line,
        "platform_text": current.platform_text,
    }
    if not current.distinguish_main:
        return patterns.PatternStyle(**platform_colors)
    return patterns.PatternStyle(
        branch_width=current.branch.width,
        new_line_width=current.branch.width,
        new_line_color=current.branch.color,
        taper_length=current.taper_length,
        **platform_colors,
    )


class ToolBase:
    """工具基类：事件返回 True 表示已处理，否则交给视图默认行为。"""

    tool_id = "tool"
    name = "工具"

    def __init__(self, manager: "ToolManager"):
        self.manager = manager

    # 便捷访问
    @property
    def scene(self):
        return self.manager.scene

    @property
    def document(self):
        return self.manager.document

    @property
    def view(self):
        return self.manager.view

    def step_hint(self, text: str) -> None:
        """发布当前步骤指引：同时进右侧绘制指引面板与状态栏。"""
        self.manager.set_hint(text)

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def mouse_press(self, event, pos: QPointF) -> bool:
        return False

    def mouse_move(self, event, pos: QPointF) -> bool:
        return False

    def mouse_release(self, event, pos: QPointF) -> bool:
        return False

    def mouse_double(self, event, pos: QPointF) -> bool:
        return False

    def cancel(self) -> None:
        pass

    def finish_chain(self) -> None:
        pass


class ToolManager(QObject):
    """工具切换与事件分发（场景/文档可随工程切换而更新）。"""

    toolChanged = Signal(str)
    message = Signal(str)  # 给状态栏看的提示
    hintChanged = Signal(str)  # 当前步骤指引（右侧绘制指引面板）

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.scene = None
        self.document = None
        self._tools: dict[str, ToolBase] = {}
        self._current: ToolBase | None = None
        self._current_id = "select"
        self._hint = ""

    # ---------------- 上下文 ----------------
    def set_context(self, scene, document) -> None:
        if self._current is not None:
            self._current.deactivate()
        self.scene = scene
        self.document = document
        self._tools.clear()
        self._current = None
        self.set_tool(self._current_id, force=True)

    def set_tool(self, tool_id: str, force: bool = False) -> None:
        if tool_id not in TOOL_SPEC_MAP:
            tool_id = "select"
        if tool_id == self._current_id and self._current is not None and not force:
            return
        if self._current is not None:
            self._current.deactivate()
        self._current_id = tool_id
        tool = self._tools.get(tool_id)
        if tool is None:
            tool = self._create_tool(tool_id)
            self._tools[tool_id] = tool
        self._current = tool
        self._hint = ""
        if self.scene is not None:
            tool.activate()  # 各工具在此发布第 1 步指引
        self.set_hint(self._hint or TOOL_SPEC_MAP[tool_id].hint)
        self.view.apply_tool_cursor()
        self.toolChanged.emit(tool_id)

    # ---------------- 绘制指引 ----------------
    def set_hint(self, text: str) -> None:
        """发布当前步骤指引：进右侧指引面板，同时作为状态栏提示。"""
        text = str(text or "")
        if text == self._hint:
            return
        self._hint = text
        self.hintChanged.emit(text)
        if text:
            self.message.emit(text)

    def hint(self) -> str:
        return self._hint

    def current_id(self) -> str:
        return self._current_id

    def current(self) -> ToolBase | None:
        return self._current

    def _create_tool(self, tool_id: str) -> ToolBase:
        spec = TOOL_SPEC_MAP[tool_id]
        if tool_id == "select":
            return SelectTool(self)
        if tool_id == "segment":
            return SegmentTool(self)
        if tool_id == "platform":
            return RectTool(self, spec)
        if tool_id == "section_marker":
            return BandTool(self, spec)
        if tool_id in PATTERN_TOOL_IDS:
            return PatternTool(self, spec)
        if tool_id in CONNECTOR_TOOL_IDS:
            return ConnectorTool(self, spec)
        if (spec.preset or {}).get("kind"):
            return TurnoutTool(self, spec)
        return PlaceTool(self, spec)

    # ---------------- 事件分发 ----------------
    def dispatch_press(self, event, pos: QPointF) -> bool:
        return bool(self._current is not None and self._current.mouse_press(event, pos))

    def dispatch_move(self, event, pos: QPointF) -> bool:
        return bool(self._current is not None and self._current.mouse_move(event, pos))

    def dispatch_release(self, event, pos: QPointF) -> bool:
        return bool(self._current is not None and self._current.mouse_release(event, pos))

    def dispatch_double(self, event, pos: QPointF) -> bool:
        return bool(self._current is not None and self._current.mouse_double(event, pos))

    def cancel(self) -> None:
        if self._current is not None:
            self._current.cancel()

    def finish_chain(self) -> None:
        if self._current is not None:
            self._current.finish_chain()

    # ---------------- 辅助 ----------------
    def push(self, command) -> None:
        if self.document is not None:
            self.document.undo_stack.push(command)

    def view_scale(self) -> float:
        return self.view.current_scale() if self.view is not None else 1.0

    def snap_threshold(self) -> float:
        return SNAP_PX / max(self.view_scale(), 1e-6)

    def px_threshold(self, px: float) -> float:
        return px / max(self.view_scale(), 1e-6)


class SelectTool(ToolBase):
    tool_id = "select"
    name = "选择"

    def __init__(self, manager: ToolManager):
        super().__init__(manager)
        self._drag: dict | None = None

    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.step_hint("点选或框选元素：拖动移动，拖手柄改尺寸；空格+拖拽平移画布")

    def deactivate(self) -> None:
        self._finish_drag(commit=False)

    # ---------------- 命中 ----------------
    def _hit_handle(self, pos: QPointF):
        limit = self.manager.px_threshold(HANDLE_PX)
        best = None
        best_dist = limit
        for item in self.scene.selectedItems():
            if not isinstance(item, LayoutItem):
                continue
            for handle in item.handles():
                dist = geometry.distance(item.mapToScene(handle.pos), pos)
                if dist <= best_dist:
                    best, best_dist = (item, handle), dist
        return best

    def _item_at(self, pos: QPointF) -> LayoutItem | None:
        view = self.view
        item = view.itemAt(view.mapFromScene(pos))
        while item is not None and not isinstance(item, LayoutItem):
            item = item.parentItem()
        return item

    def _selected(self) -> list[LayoutItem]:
        return [item for item in self.scene.selectedItems() if isinstance(item, LayoutItem)]

    # ---------------- 事件 ----------------
    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        hit = self._hit_handle(pos)
        if hit is not None:
            item, handle = hit
            item.begin_handle_drag(handle.role)
            old = {name: item.get_prop(name) for name in item.handle_fields(handle.role)}
            self._drag = {"mode": "handle", "item": item, "role": handle.role, "old": old}
            return True
        item = self._item_at(pos)
        if item is None or not item.is_printable():
            return False  # 空白处：交给视图做橡皮筋框选
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl:
            item.setSelected(not item.isSelected())
            if not item.isSelected():
                return True
        elif not item.isSelected():
            self.scene.clearSelection()
            item.setSelected(True)
        selected = self._selected()
        self._drag = {
            "mode": "move",
            "press": QPointF(pos),
            "moved": False,
            "orig": [(it, QPointF(it.pos())) for it in selected],
            "widths": [(it, float(it.get_prop("width"))) for it in selected if isinstance(it, PlatformItem)],
            "exclude": set(selected),
        }
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        drag = self._drag
        if drag is None:
            hit = self._hit_handle(pos)
            if self.view is not None:
                self.view.setCursor(hit[1].cursor if hit is not None else Qt.CursorShape.ArrowCursor)
            return False
        if drag["mode"] == "handle":
            item = drag["item"]
            snapped = self._snap(pos, exclude={item})
            item.apply_handle(drag["role"], QPointF(snapped.pos))
            if isinstance(item, PlatformItem) and drag["role"] == "width":
                snap_platform(item, self.scene, self.manager.px_threshold(SNAP_PX))
            return True
        delta = pos - drag["press"]
        delta = self._adjust_delta(drag, delta)
        drag["moved"] = drag["moved"] or abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6
        for item, origin in drag["orig"]:
            item.setPos(origin + delta)
        for item, _origin in drag["orig"]:
            if isinstance(item, PlatformItem) and snap_platform(item, self.scene, self.manager.px_threshold(SNAP_PX)):
                drag["moved"] = True  # 吸附也会改动位置/宽度，必须记入撤销
        return True

    def mouse_release(self, event, pos: QPointF) -> bool:
        self._finish_drag(commit=True)
        return True

    def cancel(self) -> None:
        if self._drag is not None:
            self._finish_drag(commit=False)
        else:
            self.scene.clearSelection()

    # ---------------- 内部 ----------------
    def _snap(self, pos: QPointF, exclude) -> SnapResult:
        snap = self.scene.snap_point(pos, self.manager.snap_threshold(), exclude=exclude)
        self.scene.show_snap(snap)
        return snap

    def _adjust_delta(self, drag: dict, delta: QPointF) -> QPointF:
        document = self.document
        if document is None:
            return delta
        anchor_item, anchor_origin = drag["orig"][0]
        if document.snap_ports:
            best = None
            threshold = self.manager.snap_threshold()
            for port in anchor_item.ports():
                target = QPointF(port.pos) + delta
                other = self.scene.nearest_port(target, threshold, exclude=drag["exclude"])
                if other is None:
                    continue
                dist = geometry.distance(target, other.pos)
                if best is None or dist < best[0]:
                    best = (dist, port, other)
            if best is not None:
                _dist, port, other = best
                return QPointF(other.pos - port.pos)
        if document.snap_grid:
            step = document.grid_size
            if len(drag["orig"]) == 1:
                target = geometry.snap_point_to_grid(anchor_origin + delta, step)
                return target - anchor_origin
            return QPointF(geometry.snap_value(delta.x(), step), geometry.snap_value(delta.y(), step))
        return delta

    def _finish_drag(self, commit: bool) -> None:
        drag = self._drag
        self._drag = None
        if drag is None or not commit:
            return
        if drag["mode"] == "handle":
            item = drag["item"]
            props = {}
            for name, old in drag["old"].items():
                new = item.get_prop(name)
                if old != new:
                    props[name] = (old, new)
            if props:
                self.manager.push(EditPropertiesCommand(self.scene, [(item, props)], "调整形状"))
            return
        if not drag["moved"]:
            return
        widths = dict(drag.get("widths") or ())
        entries = []
        for item, origin in drag["orig"]:
            props: dict[str, tuple] = {}
            if item.pos() != origin:
                props["x"] = (origin.x(), item.pos().x())
                props["y"] = (origin.y(), item.pos().y())
            old_width = widths.get(item)
            if old_width is not None:
                new_width = float(item.get_prop("width"))
                if abs(new_width - old_width) > 1e-6:
                    props["width"] = (old_width, new_width)  # 吸附可能顺带调整站台宽度
            if props:
                entries.append((item, props))
        if entries:
            self.manager.push(EditPropertiesCommand(self.scene, entries, "移动元素", merge_key="move"))


class GhostTool(ToolBase):
    """带半透明预览对象的工具（放置/拖画共用）。"""

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager)
        self.spec = spec
        self._ghost: LayoutItem | None = None

    def _spawn_ghost(self) -> None:
        if self.scene is None or self.spec.cls is None:
            return
        ghost = self.spec.cls()
        for name, value in (self.spec.preset or {}).items():
            ghost.set_prop(name, value)
        style.apply_defaults(ghost)
        ghost.setOpacity(GHOST_OPACITY)
        ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.scene.addItem(ghost)
        self._ghost = ghost

    def _drop_ghost(self) -> None:
        ghost = self._ghost
        self._ghost = None
        if ghost is not None and ghost.scene() is not None:
            ghost.scene().removeItem(ghost)

    def _commit_ghost(self) -> LayoutItem | None:
        ghost = self._ghost
        self._ghost = None
        if ghost is None:
            return None
        ghost.setOpacity(1.0)
        ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene.clearSelection()
        ghost.setSelected(True)
        self.manager.push(AddItemsCommand(self.scene, [ghost], f"放置{self.spec.name}"))
        return ghost

    def _snap_free(self, pos: QPointF, use_grid: bool = True) -> SnapResult:
        snap = self.scene.snap_point(pos, 0.0, exclude=(), use_grid=use_grid)
        self.scene.show_snap(snap)
        return snap


class PlaceTool(GhostTool):
    """点击放置类工具：道岔、车挡、文字标注。"""

    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self._spawn_ghost()
        self.step_hint(
            f"点击放置{self.spec.name}；靠近其它元素的股道/端口会自动对齐，右键/Esc 结束"
        )

    def deactivate(self) -> None:
        self._drop_ghost()
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        if self.scene is not None:
            self.scene.show_snap(None)

    def mouse_move(self, event, pos: QPointF) -> bool:
        ghost = self._ghost
        if ghost is None:
            return False
        ghost_pos, rotation, snap = self._compute(pos)
        ghost.setPos(ghost_pos)
        ghost.setRotation(rotation)
        self.scene.show_snap(snap)
        return True

    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton or self._ghost is None:
            return False
        placed = self._commit_ghost()
        if isinstance(placed, TextItem):
            self.scene.textEditRequested.emit(placed)
        self._spawn_ghost()
        self.mouse_move(event, pos)
        return True

    def _compute(self, pos: QPointF) -> tuple[QPointF, float, SnapResult]:
        ghost = self._ghost
        threshold = self.manager.snap_threshold()
        snap = self.scene.snap_point(pos, threshold, exclude={ghost})
        rotation = ghost.rotation()
        local_ports = getattr(ghost, "local_ports", None)
        if local_ports is None or self.document is None or not self.document.snap_ports:
            return QPointF(snap.pos), rotation, snap
        ports = local_ports()
        if not ports or snap.port is None:
            return QPointF(snap.pos), rotation, snap
        target = snap.port
        # 选“回头朝向相接线”的端口作为接轨口：其出射方向与 180° 最接近
        local = min(
            ports,
            key=lambda port: (abs(geometry.signed_angle_diff(port.angle, 180.0)), abs(port.pos.x()), abs(port.pos.y())),
        )
        rotation = geometry.normalize_angle(target.angle + 180.0 - local.angle)
        offset = geometry.rotate_point(local.pos, rotation)
        ghost_pos = QPointF(target.pos.x() - offset.x(), target.pos.y() - offset.y())
        return ghost_pos, rotation, SnapResult("port", QPointF(target.pos), target)


class TurnoutTool(GhostTool):
    """道岔：两步放置——先定主线落点，再拖出曲股方向。"""

    tool_id = "turnout_single"
    name = "道岔"
    STEP_MAIN = "第 1 步：点击主线落点（贴合股道中线或吸附端口会自动对位）"
    STEP_BRANCH = "第 2 步：拖动定曲股方向后点击放置；右键/Esc 退回上一步"

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager, spec)
        self._main: SnapResult | None = None  # 非空 = 主线落点已定，正在拖曲股方向

    # ---------------- 生命周期 ----------------
    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self._spawn_ghost()
        self.step_hint(self.STEP_MAIN)

    def deactivate(self) -> None:
        self._main = None
        self._drop_ghost()
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        """右键 / Esc：退回选主线位置（幽灵保留，可继续放置）。"""
        self._main = None
        self.step_hint(self.STEP_MAIN)
        if self.scene is not None:
            self.scene.show_snap(None)

    # ---------------- 事件 ----------------
    def mouse_move(self, event, pos: QPointF) -> bool:
        ghost = self._ghost
        if ghost is None:
            return False
        if self._main is not None:
            self.scene.show_snap(self._apply_branch(ghost, pos))
            return True
        ghost_pos, rotation, snap = self._main_snap(pos)
        ghost.setPos(ghost_pos)
        ghost.setRotation(rotation)
        self.scene.show_snap(snap)
        return True

    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return True
        if event.button() != Qt.MouseButton.LeftButton or self._ghost is None:
            return False
        if self._main is None:
            ghost_pos, rotation, snap = self._main_snap(pos)
            self._ghost.setPos(ghost_pos)
            self._ghost.setRotation(rotation)
            self._main = snap
            self.scene.show_snap(snap)
            self.step_hint(self.STEP_BRANCH)
            return True
        self._apply_branch(self._ghost, pos)
        self._commit_ghost()
        self._main = None
        self._spawn_ghost()
        self.step_hint(self.STEP_MAIN)
        self.mouse_move(event, pos)
        return True

    # ---------------- 第一步：主线落点 ----------------
    def _main_snap(self, pos: QPointF) -> tuple[QPointF, float, SnapResult]:
        """优先接端口，其次贴合光标下的股道中线，最后自由落点。"""
        ghost = self._ghost
        snap = self.scene.snap_point(pos, self.manager.snap_threshold(), exclude={ghost})
        if snap.kind == "port" and snap.port is not None:
            ghost_pos, rotation = self._align_to_port(ghost, snap.port)
            return ghost_pos, rotation, snap
        track = self._track_at(pos, exclude={ghost})
        if track is not None:
            item, angle, foot = track
            offset = turnout.center_offset(str(ghost.get_prop("kind")), float(ghost.get_prop("length")))
            origin = geometry.point_from(foot, angle + 180.0, offset)
            return origin, angle, SnapResult("track", QPointF(foot), item=item)
        return QPointF(snap.pos), float(ghost.rotation()), snap

    def _align_to_port(self, ghost, port) -> tuple[QPointF, float]:
        """让“回头端口”接上目标端口，直股顺着目标端口方向。"""
        local_ports = getattr(ghost, "local_ports", None)
        if local_ports is None or self.document is None or not self.document.snap_ports:
            return QPointF(port.pos), float(ghost.rotation())
        ports = local_ports()
        if not ports:
            return QPointF(port.pos), float(ghost.rotation())
        # 出射方向与 180° 最接近的端口最像“回头口”
        local = min(
            ports,
            key=lambda item: (
                abs(geometry.signed_angle_diff(item.angle, 180.0)),
                abs(item.pos.x()),
                abs(item.pos.y()),
            ),
        )
        rotation = geometry.normalize_angle(port.angle + 180.0 - local.angle)
        offset = geometry.rotate_point(local.pos, rotation)
        return QPointF(port.pos.x() - offset.x(), port.pos.y() - offset.y()), rotation

    def _track_at(self, pos: QPointF, exclude=()) -> tuple[LayoutItem, float, QPointF] | None:
        """光标附近的股道：返回 (图元, 方向角, 中线上的垂足)，超出阈值返回 None。"""
        hit = nearest_segment(self.scene, pos, self.manager.snap_threshold(), exclude)
        if hit is None:
            return None
        item, angle, foot = hit
        return item, angle, foot

    # ---------------- 第二步：曲股方向 ----------------
    def _apply_branch(self, ghost, pos: QPointF) -> SnapResult:
        """由光标推出曲股方向：对齐光标下的端口/股道，否则按角度步长吸附。"""
        anchor = QPointF(ghost.pos())
        main = float(ghost.rotation())
        cursor = geometry.angle_of(anchor, pos)
        snap = self.scene.snap_point(pos, self.manager.snap_threshold(), exclude={ghost})
        target: float | None = None
        if snap.kind == "port" and snap.port is not None:
            # 端口出射方向的反向 = 从股道过来时的走向
            target = geometry.toward_angle(float(snap.port.angle) + 180.0, cursor)
        else:
            track = self._track_at(pos, exclude={ghost})
            if track is not None:
                item, angle, foot = track
                target = geometry.toward_angle(angle, cursor)
                snap = SnapResult("track", QPointF(foot), item=item)
        if target is None:
            step = 0.0 if self.document is None else float(self.document.angle_step)
            local = geometry.snap_angle_signed(geometry.signed_angle_diff(cursor, main), step)
        else:
            local = geometry.signed_angle_diff(target, main)
        if abs(local) < turnout.MIN_ANGLE:
            return snap  # 光标几乎落在主线上：保持当前曲股设置
        side = 1.0 if local > 0.0 else -1.0
        ghost.set_prop("branch_angle", abs(local))
        ghost.set_prop("mirror", side != turnout.base_side(str(ghost.get_prop("kind"))))
        return snap


class PatternTool(ToolBase):
    """组合配线：依次点两条股道 → 移动鼠标实时预览 → 再点一次生成。

    生成的线段/道岔/车挡都是普通图元（可单独选中、拖动、吸附），
    整组作为一次撤销步骤。
    """

    PICK_SECOND = "已选中第一条股道，请再点一条与它基本平行的相邻股道"

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager)
        self.spec = spec
        self._tracks: list[tuple[LayoutItem, patterns.Track]] = []
        self._frame: patterns.Frame | None = None
        self._data: list[dict] | None = None
        self._ghosts: list[LayoutItem] = []
        self._last_error = ""

    # ---------------- 生命周期 ----------------
    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.step_hint(self.spec.hint)

    def deactivate(self) -> None:
        self._clear_ghosts()
        self._reset_tracks()
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        """右键 / Esc：退回上一步（两条股道 → 一条 → 未选）。"""
        self._clear_ghosts()
        if self._tracks:
            item, _track = self._tracks.pop()
            item.setSelected(False)
        self._frame = None
        self._data = None
        self._last_error = ""
        self.step_hint(self.PICK_SECOND if self._tracks else self.spec.hint)
        if self.scene is not None:
            self.scene.show_snap(None)

    # ---------------- 事件 ----------------
    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if len(self._tracks) < 2:
            return self._pick(pos)
        if not self._data:
            self._refresh(pos)
        self._commit()
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        if len(self._tracks) == 2 and self._frame is not None:
            self._refresh(pos)
            return True
        hit = nearest_segment(self.scene, pos, self.manager.px_threshold(PICK_PX))
        if hit is not None:
            self.scene.show_snap(SnapResult("track", hit[2], item=hit[0]))
        return False

    # ---------------- 选股道 ----------------
    def _pick(self, pos: QPointF) -> bool:
        hit = nearest_segment(self.scene, pos, self.manager.px_threshold(PICK_PX))
        if hit is None:
            self._report(f"{self.spec.name}：请点击股道线段")
            return True
        item, _angle, _foot = hit
        if any(item is picked for picked, _track in self._tracks):
            self._report("请选择另一条股道")
            return True
        item.setSelected(True)
        self._tracks.append((item, track_of(item)))
        if len(self._tracks) < 2:
            self._report(self.PICK_SECOND)
            return True
        frame = self._make_frame()
        if frame is None:
            return True
        self._frame = frame
        self._report(f"{self.spec.name}：移动鼠标选择方向，再点击生成")
        return True

    def _make_frame(self) -> patterns.Frame | None:
        first, second = self._tracks[0][1], self._tracks[1][1]
        try:
            return patterns.make_frame(first, second)
        except patterns.PatternError as error:
            item, _track = self._tracks.pop()
            item.setSelected(False)
            self._report(str(error))
            return None

    def _reset_tracks(self) -> None:
        for item, _track in self._tracks:
            if item.scene() is not None:
                item.setSelected(False)
        self._tracks.clear()
        self._frame = None
        self._data = None

    # ---------------- 预览与生成 ----------------
    def _refresh(self, cursor: QPointF) -> None:
        frame = self._frame
        if frame is None:
            return
        t, lean = patterns.grip(frame, cursor)
        try:
            data = patterns.build(
                self.spec.tool_id,
                self._tracks[0][1],
                self._tracks[1][1],
                t,
                lean,
                pattern_style(),
            )
        except patterns.PatternError as error:
            self._clear_ghosts()
            self._data = None
            self._report(str(error))
            return
        self._last_error = ""
        self.scene.show_snap(SnapResult("track", frame.point(t, 0.0), item=self._tracks[0][0]))
        if data == self._data:
            return
        self._data = data
        self._clear_ghosts()
        for entry in data:
            ghost = registry.create_element(entry)
            ghost.setOpacity(GHOST_OPACITY)
            ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.scene.addItem(ghost)
            self._ghosts.append(ghost)

    def _commit(self) -> None:
        items = self._ghosts
        if not items:
            return
        self._ghosts = []
        for item in items:
            item.setOpacity(1.0)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.manager.push(AddItemsCommand(self.scene, items, f"生成{self.spec.name}"))
        self.scene.clearSelection()
        for item in items:
            item.setSelected(True)
        self._reset_tracks()
        self._last_error = ""
        self.step_hint(self.spec.hint)
        self.manager.message.emit(f"已生成{self.spec.name}：{len(items)} 个元素（Ctrl+Z 可撤销）")

    def _clear_ghosts(self) -> None:
        for ghost in self._ghosts:
            if ghost.scene() is not None:
                ghost.scene().removeItem(ghost)
        self._ghosts = []

    def _report(self, text: str) -> None:
        if text and text != self._last_error:
            self._last_error = text
            self.step_hint(text)


class SegmentTool(ToolBase):
    """股道线段：拖拽一次成型；连续点击可接续画线（同一撤销步骤）。"""

    tool_id = "segment"
    name = "股道线段"
    STEP_START = "第 1 步：点击定起点（也可按住直接拖拽一次成型；吸到端点可续轨）"
    STEP_END = "第 2 步：点击定终点；Shift 临时脱离角度吸附，右键/Esc 结束"

    def __init__(self, manager: ToolManager):
        super().__init__(manager)
        self._anchor: SnapResult | None = None
        self._mode = ""
        self._ghost: SegmentItem | None = None
        self._chain_open = False

    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.step_hint(self.STEP_START)

    def deactivate(self) -> None:
        self._anchor = None
        self._mode = ""
        self.finish_chain()
        self._clear_ghost()
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        self._anchor = None
        self._mode = ""
        self.finish_chain()
        self._clear_ghost()
        if self.scene is not None:
            self.scene.show_snap(None)

    # ---------------- 事件 ----------------
    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snap = self._snap(pos, anchor=self._anchor)
        self.scene.show_snap(snap)
        if self._anchor is None:
            self._anchor = snap
            self._mode = "press"
            self.step_hint(self.STEP_END)
        else:
            self._commit_segment(self._anchor, snap)
            self._anchor = snap
            self._mode = "chain"
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._anchor is None:
            self.scene.show_snap(self._snap(pos, anchor=None, free=free))
            return False
        snap = self._snap(pos, anchor=self._anchor, free=free)
        self._update_ghost(self._anchor.pos, snap.pos)
        self.scene.show_snap(snap)
        return True

    def mouse_release(self, event, pos: QPointF) -> bool:
        if self._mode == "press" and self._anchor is not None:
            free = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            snap = self._snap(pos, anchor=self._anchor, free=free)
            min_length = self.manager.px_threshold(MIN_DRAG_PX)
            if geometry.distance(self._anchor.pos, snap.pos) >= min_length:
                self._commit_segment(self._anchor, snap)
                self._anchor = None
                self.finish_chain()
            self._mode = ""
        return True

    # ---------------- 内部 ----------------
    def _snap(self, pos: QPointF, anchor: SnapResult | None, free: bool = False) -> SnapResult:
        threshold = self.manager.snap_threshold()
        snap = self.scene.snap_point(pos, threshold, exclude=())
        if snap.kind == "port" or anchor is None or free:
            return snap
        document = self.document
        if document is None or document.angle_step <= 0:
            return snap
        base = anchor.port.angle if anchor.port is not None else 0.0
        angle = base + geometry.snap_angle(geometry.angle_of(anchor.pos, pos) - base, document.angle_step)
        length = max(geometry.MIN_SEGMENT_LENGTH, geometry.project_on_direction(anchor.pos, pos, angle))
        if document.snap_grid:
            length = max(geometry.MIN_SEGMENT_LENGTH, geometry.snap_value(length, document.grid_size))
        return SnapResult("angle", geometry.point_from(anchor.pos, angle, length))

    def _update_ghost(self, start: QPointF, end: QPointF) -> None:
        if self.scene is None:
            return
        if self._ghost is None:
            self._ghost = SegmentItem()
            self._ghost.setOpacity(GHOST_OPACITY)
            self._ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.scene.addItem(self._ghost)
        length = max(geometry.MIN_SEGMENT_LENGTH, geometry.distance(start, end))
        self._ghost.setPos(start)
        self._ghost.setRotation(geometry.angle_of(start, end))
        self._ghost.set_prop("length", length)

    def _clear_ghost(self) -> None:
        ghost = self._ghost
        self._ghost = None
        if ghost is not None and ghost.scene() is not None:
            ghost.scene().removeItem(ghost)

    def _commit_segment(self, start: SnapResult, end: SnapResult) -> None:
        length = geometry.distance(start.pos, end.pos)
        if length < geometry.MIN_SEGMENT_LENGTH:
            return
        item = SegmentItem()
        item.setPos(start.pos)
        item.setRotation(geometry.angle_of(start.pos, end.pos))
        item.set_prop("length", length)
        style.apply_defaults(item)
        self.scene.addItem(item)
        if not self._chain_open and self.document is not None:
            self.document.undo_stack.beginMacro("绘制股道")
            self._chain_open = True
        self.manager.push(AddItemsCommand(self.scene, [item], "绘制线段"))
        self.scene.clearSelection()
        item.setSelected(True)
        self._clear_ghost()

    def finish_chain(self) -> None:
        if self._chain_open and self.document is not None:
            self.document.undo_stack.endMacro()
        self._chain_open = False
        if self._anchor is None:
            self.step_hint(self.STEP_START)


class ConnectorTool(GhostTool):
    """联络线：依次点两条交叉的股道 → 移动鼠标定两个接点 → 再点一次生成。

    光标相对交叉点的位置决定两个接点：沿每条股道各自的投影（网格吸附）即为接点，
    曲线型还会顺着两条股道各自的走向出/入（examples/example6 的画法）。
    只新增联络线本身，不改动原有股道。
    """

    PICK_SECOND = "已选中第一条股道，请再点一条与它交叉的股道"

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager, spec)
        self._lines: list[tuple[LayoutItem, QPointF, QPointF, float]] = []
        self._cross: QPointF | None = None
        self._data: dict | None = None
        self._last_error = ""

    # ---------------- 生命周期 ----------------
    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.step_hint(self.spec.hint)

    def deactivate(self) -> None:
        self._drop_ghost()
        self._reset()
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        """右键 / Esc：退回上一步（两条股道 → 一条 → 未选）。"""
        self._drop_ghost()
        self._data = None
        self._cross = None
        if self._lines:
            item = self._lines.pop()[0]
            if item.scene() is not None:
                item.setSelected(False)
        self._last_error = ""
        self.step_hint(self.PICK_SECOND if self._lines else self.spec.hint)
        if self.scene is not None:
            self.scene.show_snap(None)

    # ---------------- 事件 ----------------
    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if len(self._lines) < 2:
            return self._pick(pos)
        if self._data is None:
            self._refresh(pos)
        self._commit()
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        if len(self._lines) == 2:
            self._refresh(pos)
            return True
        hit = nearest_segment(self.scene, pos, self.manager.px_threshold(PICK_PX))
        if hit is not None:
            self.scene.show_snap(SnapResult("track", hit[2], item=hit[0]))
        return False

    # ---------------- 选股道 ----------------
    def _pick(self, pos: QPointF) -> bool:
        hit = nearest_segment(self.scene, pos, self.manager.px_threshold(PICK_PX))
        if hit is None or not isinstance(hit[0], SegmentItem):
            self._report(f"{self.spec.name}：请点击股道线段")
            return True
        item = hit[0]
        if any(item is line[0] for line in self._lines):
            self._report("请选择另一条股道")
            return True
        item.setSelected(True)
        self._lines.append(self._line_of(item))
        if len(self._lines) < 2:
            self._report(self.PICK_SECOND)
            return True
        cross = self._crossing()
        if cross is None:
            self.cancel()
            self._report("两条股道没有交叉：请点一条与它交叉的股道")
            return True
        self._cross = cross
        self._report(f"{self.spec.name}：移动鼠标调整两个接点，点击生成")
        return True

    @staticmethod
    def _line_of(item: LayoutItem) -> tuple[LayoutItem, QPointF, QPointF, float]:
        start = item.mapToScene(QPointF(0.0, 0.0))
        end = item.mapToScene(QPointF(float(item.get_prop("length")), 0.0))
        return item, start, end, geometry.angle_of(start, end)

    def _crossing(self) -> QPointF | None:
        _item_a, a_start, a_end, _angle_a = self._lines[0]
        _item_b, b_start, b_end, _angle_b = self._lines[1]
        hit = geometry.segment_intersection(a_start, a_end, b_start, b_end, CONNECTOR_MIN_CROSS_ANGLE)
        return None if hit is None else hit[0]

    # ---------------- 预览与生成 ----------------
    def _attachments(self, cursor: QPointF) -> tuple[QPointF, QPointF, float, float] | None:
        """由光标推出 (起点, 终点, 起点切向角, 终点切向角)（切向角相对弦线）。"""
        cross = self._cross
        if cross is None:
            return None
        _item_a, _a_start, _a_end, angle_a = self._lines[0]
        _item_b, _b_start, _b_end, angle_b = self._lines[1]
        snap = self.scene.snap_point(cursor, self.manager.snap_threshold())
        base = snap.pos
        t_a = geometry.project_on_direction(cross, base, angle_a)
        t_b = geometry.project_on_direction(cross, base, angle_b)
        document = self.document
        if snap.kind != "port" and document is not None and document.snap_grid:
            t_a = geometry.snap_value(t_a, float(document.grid_size))
            t_b = geometry.snap_value(t_b, float(document.grid_size))
        if abs(t_a) < CONNECTOR_MIN_OFFSET or abs(t_b) < CONNECTOR_MIN_OFFSET:
            self._report("接点离交叉点太近：请把光标移到交叉点的一侧")
            return None
        start = geometry.point_from(cross, angle_a, t_a)
        end = geometry.point_from(cross, angle_b, t_b)
        if geometry.distance(start, end) < geometry.MIN_SEGMENT_LENGTH:
            self._report("两个接点几乎重合：请把光标移远一些")
            return None
        rotation = geometry.angle_of(start, end)
        # 起点顺着第一条股道指向交叉点，终点顺着第二条股道离开交叉点
        tangent_a = angle_a if t_a < 0.0 else angle_a + 180.0
        tangent_b = angle_b if t_b > 0.0 else angle_b + 180.0
        return (
            start,
            end,
            geometry.signed_angle_diff(tangent_a, rotation),
            geometry.signed_angle_diff(tangent_b, rotation),
        )

    def _refresh(self, cursor: QPointF) -> None:
        attach = self._attachments(cursor)
        if attach is None:
            return
        start, end, start_angle, end_angle = attach
        if self._ghost is None:
            self._spawn_ghost()
        ghost = self._ghost
        if ghost is None:
            return
        rotation = geometry.angle_of(start, end)
        length = geometry.distance(start, end)
        ghost.setPos(start)
        ghost.setRotation(rotation)
        ghost.set_prop("length", length)
        ghost.set_prop("start_angle", start_angle)
        ghost.set_prop("end_angle", end_angle)
        self._data = {
            "start": start,
            "length": length,
            "rotation": rotation,
            "start_angle": start_angle,
            "end_angle": end_angle,
        }
        self._last_error = ""
        self.scene.show_snap(SnapResult("track", QPointF(end), item=self._lines[1][0]))

    def _commit(self) -> None:
        if self._data is None or self._ghost is None:
            return
        placed = self._commit_ghost()
        if placed is None:
            return
        self._reset()
        self.step_hint(self.spec.hint)
        self.manager.message.emit(f"已生成{self.spec.name}（Ctrl+Z 可撤销）")

    def _reset(self) -> None:
        for item, *_rest in self._lines:
            if item.scene() is not None:
                item.setSelected(False)
        self._lines.clear()
        self._cross = None
        self._data = None
        self._last_error = ""

    def _report(self, text: str) -> None:
        if text and text != self._last_error:
            self._last_error = text
            self.step_hint(text)


class RectTool(GhostTool):
    """站台：拖出轴对齐矩形范围。"""

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager, spec)
        self._start: QPointF | None = None

    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.step_hint(f"拖出{self.spec.name}范围：按住左键拖拽定大小，松开完成（可吸网格/端点）")

    def deactivate(self) -> None:
        self._drop_ghost()
        self._start = None

    def cancel(self) -> None:
        self._drop_ghost()
        self._start = None

    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start = QPointF(self._snap_free(pos).pos)
        self.step_hint("拖到合适大小后松开左键完成；之后可用手柄调长度/宽度")
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        if self._start is None:
            return False
        end = QPointF(self._snap_free(pos).pos)
        self._update_ghost(self._start, end)
        return True

    def mouse_release(self, event, pos: QPointF) -> bool:
        if self._start is None:
            return False
        start = self._start
        end = QPointF(self._snap_free(pos).pos)
        self._start = None
        min_size = self.manager.px_threshold(MIN_DRAG_PX)
        if max(abs(end.x() - start.x()), abs(end.y() - start.y())) < min_size:
            self._drop_ghost()
            return True
        self._update_ghost(start, end)
        self._commit_ghost()
        self._spawn_ghost()
        return True

    def _update_ghost(self, p0: QPointF, p1: QPointF) -> None:
        if self._ghost is None:
            self._spawn_ghost()
        ghost = self._ghost
        if ghost is None:
            return
        x0, x1 = sorted((p0.x(), p1.x()))
        y0, y1 = sorted((p0.y(), p1.y()))
        width = max(x1 - x0, geometry.MIN_RECT_LENGTH)
        height = max(y1 - y0, geometry.MIN_RECT_WIDTH)
        if width >= height:
            ghost.setPos(x0, (y0 + y1) / 2.0)
            ghost.setRotation(0.0)
            ghost.set_prop("length", width)
            ghost.set_prop("width", height)
        else:
            ghost.setPos((x0 + x1) / 2.0, y0)
            ghost.setRotation(90.0)
            ghost.set_prop("length", height)
            ghost.set_prop("width", width)
        if isinstance(ghost, PlatformItem):
            # 长边靠近平行股道时按默认间隔吸附（预览与最终结果一致）
            snap_platform(ghost, self.scene, self.manager.px_threshold(SNAP_PX))


class BandTool(GhostTool):
    """区间标记：沿吸附方向拖拽出长度（宽度用默认值）。"""

    def __init__(self, manager: ToolManager, spec: ToolSpec):
        super().__init__(manager, spec)
        self._start: SnapResult | None = None

    def activate(self) -> None:
        if self.view is not None:
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.step_hint(f"第 1 步：点击定{self.spec.name}起点（可吸附端点/端口）")

    def deactivate(self) -> None:
        self._drop_ghost()
        self._start = None
        if self.scene is not None:
            self.scene.show_snap(None)

    def cancel(self) -> None:
        self._drop_ghost()
        self._start = None
        if self.scene is not None:
            self.scene.show_snap(None)

    def mouse_press(self, event, pos: QPointF) -> bool:
        if event.button() == Qt.MouseButton.RightButton:
            self.cancel()
            return True
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start = self._snap_free(pos)
        self.step_hint("第 2 步：沿方向拖拽定长度，松开完成；Shift 脱离角度吸附")
        return True

    def mouse_move(self, event, pos: QPointF) -> bool:
        if self._start is None:
            self._snap_free(pos)
            return False
        snap = self._band_snap(self._start, pos)
        self._update_ghost(snap)
        self.scene.show_snap(snap)
        return True

    def mouse_release(self, event, pos: QPointF) -> bool:
        if self._start is None:
            return False
        start = self._start
        snap = self._band_snap(start, pos)
        if geometry.distance(start.pos, snap.pos) < self.manager.px_threshold(MIN_DRAG_PX):
            self._start = None
            self._drop_ghost()
            return True
        self._update_ghost(snap)
        self._start = None
        self._commit_ghost()
        self._spawn_ghost()
        return True

    def _band_snap(self, start: SnapResult, pos: QPointF) -> SnapResult:
        document = self.document
        if document is None or document.angle_step <= 0:
            return SnapResult("free", QPointF(pos))
        base = start.port.angle if start.port is not None else 0.0
        angle = base + geometry.snap_angle(geometry.angle_of(start.pos, pos) - base, document.angle_step)
        length = max(geometry.MIN_RECT_LENGTH, geometry.project_on_direction(start.pos, pos, angle))
        if document.snap_grid:
            length = max(geometry.MIN_RECT_LENGTH, geometry.snap_value(length, document.grid_size))
        return SnapResult("angle", geometry.point_from(start.pos, angle, length))

    def _update_ghost(self, end: SnapResult) -> None:
        if self._ghost is None:
            self._spawn_ghost()
        ghost = self._ghost
        start = self._start
        if ghost is None or start is None:
            return
        length = max(geometry.MIN_RECT_LENGTH, geometry.distance(start.pos, end.pos))
        ghost.setPos(start.pos)
        ghost.setRotation(geometry.angle_of(start.pos, end.pos))
        ghost.set_prop("length", length)
