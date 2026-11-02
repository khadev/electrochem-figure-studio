"""Interactive canvas (QGraphicsView/Scene) for the 3D-render schematic."""
from __future__ import annotations

import io
import math
import os

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QGraphicsLineItem, QGraphicsPixmapItem,
                             QGraphicsScene, QGraphicsView, QMessageBox)

from core import asset_library
from .items import ArrowItem, ComponentItem, MOLECULES, MoleculeItem, TextItem

DEFAULT_SCENE = QRectF(0, 0, 1200, 800)
ANNOTATION_TYPES = (MoleculeItem, TextItem, ArrowItem, ComponentItem)
BASE_Z = 10

TOOL_SELECT, TOOL_PAN, TOOL_ARROW = "select", "pan", "arrow"
TOOLS = (TOOL_SELECT, TOOL_PAN, TOOL_ARROW)


class CanvasScene(QGraphicsScene):
    """Scene carrying grid/snap settings that the items consult while dragging."""

    layers_changed = pyqtSignal()      # items added/removed/renamed/re-ordered/locked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_visible = False
        self.snap_enabled = True
        self.grid_size = 25
        self.user_dragging = False     # set by the view while the mouse is down

    @property
    def snapping_active(self) -> bool:
        return self.grid_visible and self.snap_enabled and self.user_dragging


class CanvasView(QGraphicsView):
    tool_changed = pyqtSignal(str)
    arrow_mode_changed = pyqtSignal(bool)      # kept for backwards compatibility

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = CanvasScene(self)
        self._scene.setSceneRect(DEFAULT_SCENE)
        self.setScene(self._scene)

        self._bg_item: QGraphicsPixmapItem | None = None
        self._bg_path: str | None = None
        self._tool = TOOL_SELECT
        self._arrow_start: QPointF | None = None
        self._preview: QGraphicsLineItem | None = None
        self._pan_last = None
        self._fit_mode = True

        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform |
                            QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(250)
        self.setAcceptDrops(True)          # library thumbnails / image files

    # ------------------------------------------------------------ properties
    @property
    def tool(self) -> str:
        return self._tool

    @property
    def grid_visible(self) -> bool:
        return self._scene.grid_visible

    @property
    def snap_enabled(self) -> bool:
        return self._scene.snap_enabled

    @property
    def grid_size(self) -> int:
        return self._scene.grid_size

    @property
    def background_path(self) -> str | None:
        return self._bg_path

    def background_name(self) -> str | None:
        return os.path.basename(self._bg_path) if self._bg_path else None

    # ------------------------------------------------------------------ grid
    def set_grid_visible(self, visible: bool):
        self._scene.grid_visible = bool(visible)
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool):
        self._scene.snap_enabled = bool(enabled)

    def set_grid_size(self, size: int):
        self._scene.grid_size = max(2, int(size))
        self.viewport().update()

    def _snap_point(self, p: QPointF) -> QPointF:
        if not (self._scene.grid_visible and self._scene.snap_enabled):
            return p
        g = float(self._scene.grid_size)
        return QPointF(math.floor(p.x() / g + 0.5) * g, math.floor(p.y() / g + 0.5) * g)

    # --------------------------------------------------------------- drawing
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor("#d9dce1"))
        painter.fillRect(self.sceneRect(), QColor("white"))
        painter.setPen(QPen(QColor("#9aa0a8"), 0))
        painter.drawRect(self.sceneRect())

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Grid overlay (view-only; never part of the exported figure)."""
        super().drawForeground(painter, rect)
        if not self._scene.grid_visible:
            return
        g = float(self._scene.grid_size)
        if g * self.transform().m11() < 4:          # too dense to be useful
            return
        sr = self.sceneRect()
        r = rect.intersected(sr)
        if r.isEmpty():
            return
        minor = QPen(QColor(30, 90, 170, 70), 0)
        major = QPen(QColor(30, 90, 170, 140), 0)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for i in range(math.floor(r.left() / g), math.ceil(r.right() / g) + 1):
            x = i * g
            if sr.left() <= x <= sr.right():
                painter.setPen(major if i % 5 == 0 else minor)
                painter.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        for j in range(math.floor(r.top() / g), math.ceil(r.bottom() / g) + 1):
            y = j * g
            if sr.top() <= y <= sr.bottom():
                painter.setPen(major if j % 5 == 0 else minor)
                painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

    def _item_scale(self) -> float:
        """Scale factor so newly added items suit the size of the loaded image."""
        return max(1.0, self._scene.sceneRect().width() / 900.0)

    def _view_center(self) -> QPointF:
        return self.mapToScene(self.viewport().rect().center())

    # ------------------------------------------------------------ layer API
    def annotation_items(self) -> list:
        """Molecules/text/arrows ordered bottom -> top (ascending z)."""
        items = [i for i in self._scene.items() if isinstance(i, ANNOTATION_TYPES)]
        return sorted(items, key=lambda i: i.zValue())

    def selected_annotation_items(self) -> list:
        return [i for i in self._scene.selectedItems() if isinstance(i, ANNOTATION_TYPES)]

    def _next_z(self) -> float:
        items = self.annotation_items()
        return (items[-1].zValue() + 1) if items else BASE_Z

    def _renormalize_z(self):
        for n, item in enumerate(self.annotation_items()):
            item.setZValue(BASE_Z + n)

    def _notify(self):
        self._scene.layers_changed.emit()

    def select_items(self, items):
        """Select exactly `items` on the canvas (used by the layers panel)."""
        wanted = [i for i in items if i.scene() is self._scene]
        self._scene.blockSignals(True)
        self._scene.clearSelection()
        for item in wanted:
            item.setSelected(True)
        self._scene.blockSignals(False)
        self._scene.selectionChanged.emit()      # one clean notification

    def move_z(self, items, delta: int):
        """Move items one step towards the front (delta>0) or back (delta<0)."""
        order = self.annotation_items()
        chosen = {id(i) for i in items}
        if delta > 0:
            for k in range(len(order) - 2, -1, -1):
                if id(order[k]) in chosen and id(order[k + 1]) not in chosen:
                    order[k], order[k + 1] = order[k + 1], order[k]
        else:
            for k in range(1, len(order)):
                if id(order[k]) in chosen and id(order[k - 1]) not in chosen:
                    order[k], order[k - 1] = order[k - 1], order[k]
        for n, item in enumerate(order):
            item.setZValue(BASE_Z + n)
        self._scene.update()
        self._notify()

    def set_locked(self, items, locked: bool):
        for item in items:
            item.set_locked(locked)
        self._notify()

    def toggle_lock(self, items):
        """Lock all given items, or unlock them if they are all already locked."""
        items = [i for i in items if hasattr(i, "set_locked")]
        if items:
            self.set_locked(items, not all(i.locked for i in items))

    # -------------------------------------------------------- scene content
    def _set_background(self, path: str) -> bool:
        """Load `path` as background (no dialogs). Returns success."""
        pix = QPixmap(path)
        if pix.isNull():
            return False
        if self._bg_item is not None:
            self._scene.removeItem(self._bg_item)
        self._bg_item = QGraphicsPixmapItem(pix)
        self._bg_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._bg_item.setZValue(-1000)
        self._scene.addItem(self._bg_item)
        self._scene.setSceneRect(QRectF(pix.rect()))
        self._bg_path = os.path.abspath(path)
        return True

    def load_background_image(self, path: str | None = None) -> bool:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load 3D Render", "",
                "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;All files (*)")
            if not path:
                return False
        if not self._set_background(path):
            QMessageBox.warning(self, "Load failed", f"Could not read image:\n{path}")
            return False
        self.fit_to_scene()
        self._notify()
        return True

    def _add_item(self, item, center: bool = True, at: QPointF | None = None):
        """Add `item` on top. `at` (scene coords) puts the item's centre exactly there."""
        item.setZValue(self._next_z())
        self._scene.addItem(item)
        if at is not None:
            item.setPos(at - item.transformOriginPoint())
        elif center:
            item.setPos(self._view_center() - item.boundingRect().center())
        self._scene.clearSelection()
        item.setSelected(True)
        self._notify()
        return item

    def add_molecule(self, kind: str) -> MoleculeItem:
        item = MoleculeItem(kind)
        item.setScale(1.6 * self._item_scale())
        return self._add_item(item)

    def add_text(self, text: str = "Label") -> TextItem:
        return self._add_item(TextItem(text, pixel_size=int(26 * self._item_scale())))

    def add_arrow(self, start: QPointF, end: QPointF) -> ArrowItem:
        item = ArrowItem(start, end, width=4.0 * self._item_scale())
        return self._add_item(item, center=False)

    def add_component(self, path: str, at: QPointF | None = None) -> ComponentItem:
        """Insert a library image. `at` = scene position for its centre (None = view
        centre). The position snaps to the grid when snapping is active."""
        item = ComponentItem(path)
        rect = self._scene.sceneRect()
        pw, ph = max(1.0, item.pixmap().width()), max(1.0, item.pixmap().height())
        # fit inside a box of 25 % canvas width x 40 % canvas height (never enlarge > 4x)
        fit = min(0.25 * rect.width() / pw, 0.40 * rect.height() / ph, 4.0)
        item.setScale(max(0.01, fit))
        if at is not None:
            at = self._snap_point(at)
        return self._add_item(item, center=at is None, at=at)

    def clear_canvas(self):
        self._scene.blockSignals(True)
        self._scene.clear()
        self._scene.blockSignals(False)
        self._bg_item = None
        self._bg_path = None
        self._preview = None
        self._scene.setSceneRect(DEFAULT_SCENE)
        self.fit_to_scene()
        self._scene.selectionChanged.emit()
        self._notify()

    def delete_selected(self):
        removed = False
        for item in self._scene.selectedItems():
            if isinstance(item, ANNOTATION_TYPES):
                self._scene.removeItem(item)
                removed = True
        if removed:
            self._notify()

    def scale_selected(self, factor: float):
        for item in self._scene.selectedItems():
            if isinstance(item, (MoleculeItem, TextItem)):
                item.setScale(item.scale() * factor)

    # --------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        """Snapshot of the whole canvas as a plain (JSON-ready) dictionary."""
        rect = self._scene.sceneRect()
        items = self.annotation_items()
        return {
            "canvas": {"width": rect.width(), "height": rect.height()},
            "background": ({"path": self._bg_path, "absolute_path": self._bg_path}
                           if self._bg_path else None),
            "grid": {"visible": self._scene.grid_visible,
                     "size": self._scene.grid_size,
                     "snap": self._scene.snap_enabled},
            "molecules": [i.to_dict() for i in items if isinstance(i, MoleculeItem)],
            "texts": [i.to_dict() for i in items if isinstance(i, TextItem)],
            "arrows": [i.to_dict() for i in items if isinstance(i, ArrowItem)],
            "components": [i.to_dict() for i in items if isinstance(i, ComponentItem)],
        }

    def from_dict(self, data: dict) -> list[str]:
        """Rebuild the scene from a normalised project dict. Returns warnings."""
        warnings: list[str] = []
        self.clear_canvas()
        self._scene.blockSignals(True)

        bg = data.get("background")
        if bg and bg.get("resolved_path"):
            if not self._set_background(bg["resolved_path"]):
                warnings.append(f"Could not read background image: {bg['resolved_path']}")
        canvas = data.get("canvas", {})
        if canvas.get("width", 0) > 0 and canvas.get("height", 0) > 0:
            self._scene.setSceneRect(QRectF(0, 0, canvas["width"], canvas["height"]))

        for m in data.get("molecules", []):
            if m["kind"] not in MOLECULES:
                warnings.append(f"Unknown molecule type skipped: {m['kind']}")
                continue
            self._scene.addItem(MoleculeItem.from_dict(m))
        for t in data.get("texts", []):
            self._scene.addItem(TextItem.from_dict(t))
        for a in data.get("arrows", []):
            self._scene.addItem(ArrowItem.from_dict(a))
        for c in data.get("components", []):
            item = ComponentItem.from_dict(c)
            if item.missing and c.get("resolved_path"):
                warnings.append(f"Could not read component image: {c['resolved_path']}")
            self._scene.addItem(item)

        self._renormalize_z()
        self._scene.clearSelection()
        self._scene.blockSignals(False)

        grid = data.get("grid", {})
        self.set_grid_size(grid.get("size", 25))
        self.set_snap_enabled(grid.get("snap", True))
        self.set_grid_visible(grid.get("visible", False))

        self.fit_to_scene()
        self._scene.selectionChanged.emit()
        self._notify()
        return warnings

    # ----------------------------------------------------------------- tools
    # ----------------------------------------------------- drag & drop (library)
    @staticmethod
    def _drop_payloads(mime) -> list[tuple[str, str]]:
        """[(kind, path)] carried by a drag: library assets or image files from the OS."""
        if mime.hasFormat(asset_library.ASSET_MIME):
            return asset_library.decode_assets(bytes(mime.data(asset_library.ASSET_MIME)))
        out = []
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile() and asset_library.is_image_file(url.toLocalFile()) \
                        and os.path.isfile(url.toLocalFile()):
                    out.append((asset_library.KIND_COMPONENT, url.toLocalFile()))
        return out

    def dragEnterEvent(self, event):
        if self._drop_payloads(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drop_payloads(event.mimeData()):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        payloads = self._drop_payloads(event.mimeData())
        if not payloads:
            super().dropEvent(event)
            return
        drop_pt = self.mapToScene(event.position().toPoint())
        self.set_tool(TOOL_SELECT)
        offset = 0.0
        for kind, path in payloads:
            if kind == asset_library.KIND_BACKGROUND:
                self.load_background_image(path)
            else:
                self.add_component(path, at=drop_pt + QPointF(offset, offset))
                offset += 24.0 * self._item_scale()      # stagger multi-item drops
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.setFocus()

    def set_tool(self, tool: str):
        if tool not in TOOLS or tool == self._tool:
            return
        self._tool = tool
        if tool == TOOL_SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if tool == TOOL_PAN
                                      else Qt.CursorShape.CrossCursor)
        if tool == TOOL_ARROW:
            self._scene.clearSelection()
        self.tool_changed.emit(tool)
        self.arrow_mode_changed.emit(tool == TOOL_ARROW)

    def set_arrow_mode(self, enabled: bool):
        """Backward-compatible wrapper around set_tool()."""
        if enabled:
            self.set_tool(TOOL_ARROW)
        elif self._tool == TOOL_ARROW:
            self.set_tool(TOOL_SELECT)

    # ---------------------------------------------------------- view control
    def fit_to_scene(self):
        self._fit_mode = True
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self._fit_mode = False
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    # ------------------------------------------------------------- mouse/keys
    def _rest_cursor(self):
        return {TOOL_PAN: Qt.CursorShape.OpenHandCursor,
                TOOL_ARROW: Qt.CursorShape.CrossCursor}.get(self._tool, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        btn = event.button()
        if btn == Qt.MouseButton.MiddleButton or \
                (btn == Qt.MouseButton.LeftButton and self._tool == TOOL_PAN):
            self._pan_last = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._tool == TOOL_ARROW and btn == Qt.MouseButton.LeftButton:
            self._arrow_start = self._snap_point(self.mapToScene(event.position().toPoint()))
            self._preview = QGraphicsLineItem(QLineF(self._arrow_start, self._arrow_start))
            self._preview.setPen(QPen(QColor("#1f55d6"), 3 * self._item_scale(),
                                      Qt.PenStyle.DashLine))
            self._scene.addItem(self._preview)
            event.accept()
            return
        if btn == Qt.MouseButton.LeftButton:
            self._scene.user_dragging = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_last is not None:
            delta = event.position().toPoint() - self._pan_last
            self._pan_last = event.position().toPoint()
            self._fit_mode = False
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._preview is not None and self._arrow_start is not None:
            end = self._snap_point(self.mapToScene(event.position().toPoint()))
            self._preview.setLine(QLineF(self._arrow_start, end))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._scene.user_dragging = False
        if self._pan_last is not None and event.button() in (Qt.MouseButton.MiddleButton,
                                                             Qt.MouseButton.LeftButton):
            self._pan_last = None
            self.viewport().setCursor(self._rest_cursor())
            event.accept()
            return
        if self._preview is not None and event.button() == Qt.MouseButton.LeftButton:
            end = self._snap_point(self.mapToScene(event.position().toPoint()))
            start = self._arrow_start
            self._scene.removeItem(self._preview)
            self._preview = None
            self._arrow_start = None
            if QLineF(start, end).length() > 8:
                self.add_arrow(start, end)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        focus = self._scene.focusItem()
        editing = isinstance(focus, TextItem) and focus.is_editing()
        if key == Qt.Key.Key_Escape and self._tool != TOOL_SELECT:
            self.set_tool(TOOL_SELECT)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not editing:
            self.delete_selected()
        else:
            super().keyPressEvent(event)

    # ----------------------------------------------------------------- export
    def export_to_pil(self, width_px: int = 2400) -> Image.Image:
        """Render the whole scene (no selection boxes, no grid) into a PIL image."""
        rect = self._scene.sceneRect()
        w = int(width_px)
        h = max(1, int(round(w * rect.height() / rect.width())))

        selected = self._scene.selectedItems()
        self._scene.blockSignals(True)
        self._scene.clearSelection()
        self._scene.clearFocus()          # finishes any in-progress text edit
        self._scene.blockSignals(False)

        qimg = QImage(w, h, QImage.Format.Format_ARGB32)
        qimg.fill(QColor("white"))
        painter = QPainter(qimg)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform |
                               QPainter.RenderHint.TextAntialiasing)
        self._scene.render(painter, QRectF(0, 0, w, h), rect)
        painter.end()

        self._scene.blockSignals(True)
        for item in selected:
            item.setSelected(True)
        self._scene.blockSignals(False)

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")
