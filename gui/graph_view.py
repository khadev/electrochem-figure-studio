"""Matplotlib CV graph embedded natively in a PyQt6 widget."""
from __future__ import annotations

import io

from PIL import Image
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from core.cv_generator import create_cv_figure, draw_cv


class GraphView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.params = ("Reversible", 0.6, 0.5)     # (type, height mA, position V)
        self.figure = create_cv_figure(*self.params)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.setMinimumHeight(220)

    def update_graph(self, cv_type: str, peak_height: float, peak_position: float):
        self.params = (cv_type, float(peak_height), float(peak_position))
        draw_cv(self.figure, *self.params)
        self.canvas.draw_idle()

    def export_to_pil(self, width_px: int = 2400) -> Image.Image:
        """Render the current figure at `width_px` wide and return a PIL image."""
        dpi = width_px / self.figure.get_figwidth()
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png", dpi=dpi, facecolor="white")
        buf.seek(0)
        return Image.open(buf).convert("RGB")
