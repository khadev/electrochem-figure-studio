"""Custom interactive QGraphicsItems: molecules, editable text, arrows, components.

Every item supports: selection, dragging, locking (``locked``), grid snapping
(driven by the owning scene), a human-readable ``layer_name()`` and
``to_dict()`` / ``from_dict()`` for project persistence.
"""
from __future__ import annotations

import math
import os

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                         QPainterPathStroker, QPen, QPixmap, QPolygonF,
                         QRadialGradient, QTextCursor, QTransform)
from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem,
                             QGraphicsTextItem, QStyle, QStyleOptionGraphicsItem)

from core import asset_library

_FLAG = QGraphicsItem.GraphicsItemFlag
_CHANGE = QGraphicsItem.GraphicsItemChange
SELECT_COLOR = QColor("#2b7fff")

# CPK colours and display radii (px at scale 1.0)
CPK = {
    "H": (QColor("#FFFFFF"), 15),
    "C": (QColor("#3a3a3a"), 22),
    "O": (QColor("#E8201A"), 20),
}

# atoms: (symbol, x, y)   bonds: (i, j, order)
MOLECULES = {
    "Methanol (CH₃OH)": {
        "atoms": [("C", 0, 0), ("O", 52, -26), ("H", -26, -36), ("H", -40, 18),
                  ("H", 8, 46), ("H", 80, -10)],
        "bonds": [(0, 1, 1), (0, 2, 1), (0, 3, 1), (0, 4, 1), (1, 5, 1)],
    },
    "Carbon dioxide (CO₂)": {
        "atoms": [("O", -62, 0), ("C", 0, 0), ("O", 62, 0)],
        "bonds": [(0, 1, 2), (1, 2, 2)],
    },
    "Hydrogen (H₂)": {
        "atoms": [("H", -17, 0), ("H", 17, 0)],
        "bonds": [(0, 1, 1)],
    },
}
MOLECULE_TYPES = list(MOLECULES.keys())


# ------------------------------------------------------------------ helpers
def _snap_pos(item, pos: QPointF) -> QPointF:
    """Snap an item's *anchor* to the scene grid while the user is dragging."""
    scene = item.scene()
    if scene is None or not getattr(scene, "snapping_active", False):
        return pos
    g = float(scene.grid_size)
    off = item.snap_anchor()
    x = math.floor((pos.x() + off.x()) / g + 0.5) * g - off.x()
    y = math.floor((pos.y() + off.y()) / g + 0.5) * g - off.y()
    return QPointF(x, y)


def _set_locked(item, locked: bool):
    item.locked = bool(locked)
    item.setFlag(_FLAG.ItemIsMovable, not item.locked)
    item.setCursor(Qt.CursorShape.ArrowCursor if item.locked else item.UNLOCKED_CURSOR)


def _notify_scene(item):
    scene = item.scene()
    if scene is not None and hasattr(scene, "layers_changed"):
        scene.layers_changed.emit()


# ----------------------------------------------------------------- molecule
class MoleculeItem(QGraphicsItem):
    """CPK-coloured ball-and-stick molecule drawn with QPainter."""

    PAD = 10
    UNLOCKED_CURSOR = Qt.CursorShape.OpenHandCursor

    def __init__(self, kind: str = MOLECULE_TYPES[0], parent=None):
        super().__init__(parent)
        if kind not in MOLECULES:
            raise ValueError(f"Unknown molecule: {kind}")
        self.kind = kind
        self.locked = False
        self._atoms = MOLECULES[kind]["atoms"]
        self._bonds = MOLECULES[kind]["bonds"]
        self.setFlags(_FLAG.ItemIsMovable | _FLAG.ItemIsSelectable |
                      _FLAG.ItemSendsGeometryChanges)
        self.setCursor(self.UNLOCKED_CURSOR)

        xs0 = [x - CPK[s][1] for s, x, _ in self._atoms]
        xs1 = [x + CPK[s][1] for s, x, _ in self._atoms]
        ys0 = [y - CPK[s][1] for s, _, y in self._atoms]
        ys1 = [y + CPK[s][1] for s, _, y in self._atoms]
        p = self.PAD
        self._rect = QRectF(min(xs0) - p, min(ys0) - p,
                            max(xs1) - min(xs0) + 2 * p, max(ys1) - min(ys0) + 2 * p)
        self.setTransformOriginPoint(self._rect.center())

    # -- layer-manager API
    def layer_name(self) -> str:
        return self.kind.split(" (")[0]

    def set_locked(self, locked: bool):
        _set_locked(self, locked)

    def snap_anchor(self) -> QPointF:
        return self.transformOriginPoint()

    # -- persistence
    def to_dict(self) -> dict:
        return {"kind": self.kind, "x": self.pos().x(), "y": self.pos().y(),
                "scale": self.scale(), "rotation": self.rotation(),
                "z": self.zValue(), "locked": self.locked}

    @classmethod
    def from_dict(cls, d: dict) -> "MoleculeItem":
        item = cls(d["kind"])
        item.setScale(d.get("scale", 1.0))
        item.setRotation(d.get("rotation", 0.0))
        item.setPos(d.get("x", 0.0), d.get("y", 0.0))
        item.setZValue(d.get("z", 10))
        item.set_locked(d.get("locked", False))
        return item

    # -- Qt
    def itemChange(self, change, value):
        if change == _CHANGE.ItemPositionChange:
            value = _snap_pos(self, value)
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        return self._rect

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHints(QPainter.RenderHint.Antialiasing |
                               QPainter.RenderHint.SmoothPixmapTransform)
        for i, j, order in self._bonds:
            _, x1, y1 = self._atoms[i]
            _, x2, y2 = self._atoms[j]
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            offsets, width = ((0.0,), 8) if order == 1 else ((-5.5, 5.5), 4.5)
            for off in offsets:
                painter.setPen(QPen(QColor("#8c8c8c"), width, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(x1 + nx * off, y1 + ny * off),
                                 QPointF(x2 + nx * off, y2 + ny * off))
        for sym, x, y in self._atoms:
            color, r = CPK[sym]
            grad = QRadialGradient(QPointF(x, y), r, QPointF(x - 0.35 * r, y - 0.35 * r))
            grad.setColorAt(0.0, color.lighter(185) if sym != "H" else QColor("#ffffff"))
            grad.setColorAt(0.55, color)
            grad.setColorAt(1.0, color.darker(160) if sym != "H" else QColor("#b5b5b5"))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(color.darker(190), 1.0))
            painter.drawEllipse(QPointF(x, y), r, r)

        if self.isSelected():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(SELECT_COLOR, 1.6, Qt.PenStyle.DashLine))
            painter.drawRect(self._rect)

    def mousePressEvent(self, event):
        if not self.locked:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.locked:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


# --------------------------------------------------------------------- text
class TextItem(QGraphicsTextItem):
    """Draggable text label; double-click to edit, click elsewhere to finish."""

    UNLOCKED_CURSOR = Qt.CursorShape.ArrowCursor

    def __init__(self, text: str = "Label", pixel_size: int = 24, parent=None):
        super().__init__(text, parent)
        self.locked = False
        font = QFont("Arial")
        font.setPixelSize(pixel_size)
        font.setBold(True)
        self.setFont(font)
        self.setDefaultTextColor(QColor("#111111"))
        self.setFlags(_FLAG.ItemIsMovable | _FLAG.ItemIsSelectable |
                      _FLAG.ItemIsFocusable | _FLAG.ItemSendsGeometryChanges)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setTransformOriginPoint(self.boundingRect().center())
        self.document().contentsChanged.connect(self._on_contents_changed)

    def _on_contents_changed(self):
        self.setTransformOriginPoint(self.boundingRect().center())
        _notify_scene(self)

    def refresh_origin(self):
        self.setTransformOriginPoint(self.boundingRect().center())

    # -- layer-manager API
    def layer_name(self) -> str:
        text = " ".join(self.toPlainText().split())
        if len(text) > 28:
            text = text[:27] + "…"
        return f"Text: {text}" if text else "Text: (empty)"

    def set_locked(self, locked: bool):
        _set_locked(self, locked)
        if self.locked and self.is_editing():
            self.clearFocus()

    def snap_anchor(self) -> QPointF:
        return self.transformOriginPoint()

    # -- persistence
    def to_dict(self) -> dict:
        f = self.font()
        return {"text": self.toPlainText(), "x": self.pos().x(), "y": self.pos().y(),
                "scale": self.scale(), "rotation": self.rotation(),
                "z": self.zValue(), "locked": self.locked,
                "color": self.defaultTextColor().name(),
                "font_family": f.family(),
                "font_size": f.pixelSize() if f.pixelSize() > 0 else int(f.pointSizeF() * 96 / 72),
                "bold": f.bold(), "italic": f.italic()}

    @classmethod
    def from_dict(cls, d: dict) -> "TextItem":
        item = cls(d.get("text", ""), int(d.get("font_size", 24)))
        font = item.font()
        font.setFamily(d.get("font_family", "Arial"))
        font.setBold(bool(d.get("bold", True)))
        font.setItalic(bool(d.get("italic", False)))
        item.setFont(font)
        item.setDefaultTextColor(QColor(d.get("color", "#111111")))
        item.refresh_origin()
        item.setScale(d.get("scale", 1.0))
        item.setRotation(d.get("rotation", 0.0))
        item.setPos(d.get("x", 0.0), d.get("y", 0.0))
        item.setZValue(d.get("z", 10))
        item.set_locked(d.get("locked", False))
        return item

    # -- editing
    def is_editing(self) -> bool:
        return self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction

    def mouseDoubleClickEvent(self, event):
        if self.locked:
            event.ignore()
            return
        if not self.is_editing():
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.setTextCursor(cursor)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.refresh_origin()

    def itemChange(self, change, value):
        if change == _CHANGE.ItemPositionChange:
            value = _snap_pos(self, value)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None):
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected   # suppress Qt's default frame
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, widget)
        if self.isSelected() or self.is_editing():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(SELECT_COLOR, 1.4, Qt.PenStyle.DashLine))
            painter.drawRect(self.boundingRect())


# -------------------------------------------------------------------- arrow
class ArrowItem(QGraphicsLineItem):
    """A straight line with a filled arrowhead (for reaction pathways)."""

    UNLOCKED_CURSOR = Qt.CursorShape.SizeAllCursor

    def __init__(self, start: QPointF, end: QPointF,
                 color: str = "#1f55d6", width: float = 4.0, parent=None):
        super().__init__(QLineF(start, end), parent)
        self.locked = False
        self._color = QColor(color)
        self._width = float(width)
        self._head = self._width * 4.5
        self.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap))
        self.setFlags(_FLAG.ItemIsMovable | _FLAG.ItemIsSelectable |
                      _FLAG.ItemSendsGeometryChanges)
        self.setCursor(self.UNLOCKED_CURSOR)

    # -- properties
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap))
        self.update()

    def width(self) -> float:
        return self._width

    def set_width(self, width: float):
        self.prepareGeometryChange()
        self._width = max(0.5, float(width))
        self._head = self._width * 4.5
        self.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                         Qt.PenCapStyle.RoundCap))
        self.update()

    # -- layer-manager API
    def layer_name(self) -> str:
        return "Arrow"

    def set_locked(self, locked: bool):
        _set_locked(self, locked)

    def snap_anchor(self) -> QPointF:
        return self.line().p1()

    # -- persistence
    def to_dict(self) -> dict:
        ln = self.line()
        return {"x1": ln.x1(), "y1": ln.y1(), "x2": ln.x2(), "y2": ln.y2(),
                "x": self.pos().x(), "y": self.pos().y(),
                "color": self._color.name(), "width": self._width,
                "z": self.zValue(), "locked": self.locked}

    @classmethod
    def from_dict(cls, d: dict) -> "ArrowItem":
        item = cls(QPointF(d["x1"], d["y1"]), QPointF(d["x2"], d["y2"]),
                   d.get("color", "#1f55d6"), d.get("width", 4.0))
        item.setPos(d.get("x", 0.0), d.get("y", 0.0))
        item.setZValue(d.get("z", 10))
        item.set_locked(d.get("locked", False))
        return item

    # -- geometry
    def itemChange(self, change, value):
        if change == _CHANGE.ItemPositionChange:
            value = _snap_pos(self, value)
        return super().itemChange(change, value)

    def _head_polygon(self) -> QPolygonF:
        line = self.line()
        length = line.length()
        if length < 1e-6:
            return QPolygonF()
        dx, dy = line.dx() / length, line.dy() / length
        tip = line.p2()
        base = QPointF(tip.x() - dx * self._head, tip.y() - dy * self._head)
        nx, ny = -dy, dx
        half = self._head * 0.45
        return QPolygonF([tip,
                          QPointF(base.x() + nx * half, base.y() + ny * half),
                          QPointF(base.x() - nx * half, base.y() - ny * half)])

    def boundingRect(self) -> QRectF:
        m = self._head + self._width + 4
        line = self.line()
        return QRectF(line.p1(), line.p2()).normalized().adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._width, 12.0))
        result = stroker.createStroke(path)
        result.addPolygon(self._head_polygon())
        return result

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = self.line()
        length = line.length()
        if length < 1e-6:
            return
        dx, dy = line.dx() / length, line.dy() / length
        shaft_end = QPointF(line.p2().x() - dx * self._head * 0.8,
                            line.p2().y() - dy * self._head * 0.8)
        if self.isSelected():
            glow = QColor(SELECT_COLOR)
            glow.setAlpha(90)
            painter.setPen(QPen(glow, self._width + 8, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(line.p1(), line.p2())
        painter.setPen(QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(line.p1(), shaft_end)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(self._color, 1))
        painter.drawPolygon(self._head_polygon())


# ---------------------------------------------------------------- component
class ComponentItem(QGraphicsPixmapItem):
    """A pre-rendered image asset (PNG/JPG with optional alpha) from the library.

    Supports dragging, selection, locking, grid snapping, uniform scale,
    opacity and horizontal/vertical flipping (both about the image centre).
    If the image file cannot be read a visible placeholder is shown instead and
    the original path is kept, so saving the project does not lose the link.
    """

    UNLOCKED_CURSOR = Qt.CursorShape.OpenHandCursor

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.source_path = os.path.abspath(path) if os.path.isfile(path) else str(path)
        self.locked = False
        self.missing = False
        self._flip_h = False
        self._flip_v = False

        pix = QPixmap(self.source_path)
        if pix.isNull():
            pix = self._placeholder_pixmap(self.source_path)
            self.missing = True
        self.setPixmap(pix)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setFlags(_FLAG.ItemIsMovable | _FLAG.ItemIsSelectable |
                      _FLAG.ItemSendsGeometryChanges)
        self.setCursor(self.UNLOCKED_CURSOR)
        self.setTransformOriginPoint(QPointF(pix.width() / 2.0, pix.height() / 2.0))

    @staticmethod
    def _placeholder_pixmap(path: str) -> QPixmap:
        pix = QPixmap(240, 150)
        pix.fill(QColor("#f6dcdc"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#c0392b"), 3))
        p.drawRect(1, 1, 238, 148)
        p.drawLine(1, 1, 239, 149)
        p.drawLine(239, 1, 1, 149)
        p.setPen(QColor("#7b241c"))
        font = QFont("Arial")
        font.setPixelSize(15)
        font.setBold(True)
        p.setFont(font)
        p.fillRect(30, 55, 180, 40, QColor("#f6dcdc"))
        p.drawText(QRectF(30, 55, 180, 40), Qt.AlignmentFlag.AlignCenter,
                   "Missing image\n" + os.path.basename(path)[:22])
        p.end()
        return pix

    # -- flip / appearance
    @property
    def flip_h(self) -> bool:
        return self._flip_h

    @property
    def flip_v(self) -> bool:
        return self._flip_v

    def set_flip(self, horizontal: bool, vertical: bool):
        """Mirror about the image centre (the centre does not move)."""
        self._flip_h, self._flip_v = bool(horizontal), bool(vertical)
        c = self.transformOriginPoint()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.scale(-1.0 if self._flip_h else 1.0, -1.0 if self._flip_v else 1.0)
        t.translate(-c.x(), -c.y())
        self.setTransform(t)

    # -- layer-manager API
    def layer_name(self) -> str:
        name = asset_library.display_name(self.source_path)
        return f"Component: {name}" + (" (missing)" if self.missing else "")

    def set_locked(self, locked: bool):
        _set_locked(self, locked)

    def snap_anchor(self) -> QPointF:
        return self.transformOriginPoint()

    # -- persistence
    def to_dict(self) -> dict:
        return {"path": self.source_path, "absolute_path": self.source_path,
                "asset": asset_library.asset_relative_path(self.source_path),
                "x": self.pos().x(), "y": self.pos().y(),
                "scale": self.scale(), "rotation": self.rotation(),
                "opacity": self.opacity(),
                "flip_h": self._flip_h, "flip_v": self._flip_v,
                "z": self.zValue(), "locked": self.locked}

    @classmethod
    def from_dict(cls, d: dict) -> "ComponentItem":
        path = (d.get("resolved_path") or d.get("fallback_path")
                or d.get("absolute_path") or d["path"])
        item = cls(path)
        item.setScale(d.get("scale", 1.0))
        item.setRotation(d.get("rotation", 0.0))
        item.setOpacity(max(0.0, min(1.0, float(d.get("opacity", 1.0)))))
        item.set_flip(d.get("flip_h", False), d.get("flip_v", False))
        item.setPos(d.get("x", 0.0), d.get("y", 0.0))
        item.setZValue(d.get("z", 10))
        item.set_locked(d.get("locked", False))
        return item

    # -- Qt
    def itemChange(self, change, value):
        if change == _CHANGE.ItemPositionChange:
            value = _snap_pos(self, value)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if not self.locked:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.locked:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected      # use our own outline
        super().paint(painter, opt, widget)
        if self.isSelected():
            pen = QPen(SELECT_COLOR, 1.6, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)                          # constant width at any scale
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            painter.drawRect(QRectF(self.pixmap().rect()))
