"""Small vector icons drawn with QPainter (no external image files needed)."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QApplication

_ACCENT = QColor("#2b7fff")
_RED = QColor("#d64541")


def _fg() -> QColor:
    app = QApplication.instance()
    return app.palette().color(QPalette.ColorRole.WindowText) if app else QColor("#2c3e50")


def _poly(*pts) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _icon(draw) -> QIcon:
    """Draw on a 32x32 logical canvas rendered at 2x for crisp scaling."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    draw(p, _fg())
    p.end()
    return QIcon(pm)


def _pen(color, w=2.0):
    return QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _select(p, fg):
    p.setBrush(QBrush(fg))
    p.setPen(_pen(fg, 1.2))
    p.drawPolygon(_poly((8, 4), (8, 25), (13.5, 20), (17.5, 28), (21, 26.5), (17, 18.5), (24, 18)))


def _pan(p, fg):
    p.setPen(_pen(fg, 2))
    p.drawLine(16, 7, 16, 25)
    p.drawLine(7, 16, 25, 16)
    p.setBrush(QBrush(fg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(_poly((16, 2.5), (12, 8), (20, 8)))
    p.drawPolygon(_poly((16, 29.5), (12, 24), (20, 24)))
    p.drawPolygon(_poly((2.5, 16), (8, 12), (8, 20)))
    p.drawPolygon(_poly((29.5, 16), (24, 12), (24, 20)))


def _molecule(p, fg):
    p.setPen(_pen(QColor("#8c8c8c"), 3.5))
    p.drawLine(11, 20, 23, 10)
    p.setPen(QPen(QColor("#222"), 1))
    p.setBrush(QBrush(QColor("#3a3a3a")))
    p.drawEllipse(QPointF(11, 20), 7, 7)
    p.setBrush(QBrush(QColor("#e8201a")))
    p.drawEllipse(QPointF(23, 10), 5.5, 5.5)
    p.setBrush(QBrush(QColor("#ffffff")))
    p.setPen(QPen(QColor("#999"), 1))
    p.drawEllipse(QPointF(24, 24), 3.8, 3.8)


def _text(p, fg):
    f = QFont("Arial")
    f.setPixelSize(26)
    f.setBold(True)
    p.setFont(f)
    p.setPen(fg)
    p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, "T")


def _arrow(p, fg):
    p.setPen(_pen(_ACCENT, 3.2))
    p.drawLine(6, 26, 20, 12)
    p.setBrush(QBrush(_ACCENT))
    p.setPen(_pen(_ACCENT, 1))
    p.drawPolygon(_poly((27, 5), (16.5, 8.5), (23.5, 15.5)))


def _delete(p, fg):
    p.setPen(_pen(_RED, 3.5))
    p.drawLine(8, 8, 24, 24)
    p.drawLine(24, 8, 8, 24)


def _grid(p, fg):
    p.setPen(_pen(fg, 1.6))
    for v in (6, 16, 26):
        p.drawLine(v, 5, v, 27)
        p.drawLine(5, v, 27, v)


def _snap(p, fg):
    c = QColor(fg)
    c.setAlpha(110)
    p.setPen(_pen(c, 1.4))
    for v in (6, 16, 26):
        p.drawLine(v, 5, v, 27)
        p.drawLine(5, v, 27, v)
    p.setBrush(QBrush(_ACCENT))
    p.setPen(QPen(Qt.GlobalColor.white, 1.2))
    p.drawEllipse(QPointF(16, 16), 5, 5)


def _fit(p, fg):
    p.setPen(_pen(fg, 2.4))
    for (x, y, dx, dy) in ((5, 5, 1, 1), (27, 5, -1, 1), (5, 27, 1, -1), (27, 27, -1, -1)):
        p.drawLine(x, y, x + 7 * dx, y)
        p.drawLine(x, y, x, y + 7 * dy)


def _lock(p, fg):
    p.setPen(_pen(fg, 2.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(10, 4, 12, 14), 0, 180 * 16)
    p.drawLine(10, 11, 10, 15)
    p.drawLine(22, 11, 22, 15)
    p.setBrush(QBrush(fg))
    p.setPen(_pen(fg, 1))
    p.drawRoundedRect(QRectF(7, 14, 18, 14), 3, 3)


_DRAWERS = {"select": _select, "pan": _pan, "molecule": _molecule, "text": _text,
            "arrow": _arrow, "delete": _delete, "grid": _grid, "snap": _snap,
            "fit": _fit, "lock": _lock}


def get_icon(name: str) -> QIcon:
    return _icon(_DRAWERS[name])
