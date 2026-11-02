"""Right-hand dock with the CV graph controls.

(Canvas tools now live in the main toolbar, and per-item editing in the
Properties dock.)
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDockWidget, QGroupBox, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget)

from core.cv_generator import CURVE_TYPES


class ControlsDock(QDockWidget):
    update_graph_requested = pyqtSignal(str, float, float)

    def __init__(self, parent=None):
        super().__init__("Controls", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                             Qt.DockWidgetArea.LeftDockWidgetArea)
        body = QWidget()
        root = QVBoxLayout(body)

        g2 = QGroupBox("Graph Controls")
        v2 = QVBoxLayout(g2)
        v2.addWidget(QLabel("Curve type"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(CURVE_TYPES)
        v2.addWidget(self.type_combo)

        self.height_label = QLabel()
        self.height_slider = QSlider(Qt.Orientation.Horizontal)
        self.height_slider.setRange(10, 200)       # 0.10 - 2.00 mA
        self.height_slider.setValue(60)
        v2.addWidget(self.height_label)
        v2.addWidget(self.height_slider)

        self.pos_label = QLabel()
        self.pos_slider = QSlider(Qt.Orientation.Horizontal)
        self.pos_slider.setRange(20, 70)           # 0.20 - 0.70 V
        self.pos_slider.setValue(50)
        v2.addWidget(self.pos_label)
        v2.addWidget(self.pos_slider)

        self.height_slider.valueChanged.connect(self._refresh_labels)
        self.pos_slider.valueChanged.connect(self._refresh_labels)
        self._refresh_labels()

        self.update_btn = QPushButton("Update Graph")
        self.update_btn.clicked.connect(self._emit_update)
        v2.addWidget(self.update_btn)
        root.addWidget(g2)

        hint = QLabel("Ctrl+Wheel: zoom · Middle-drag: pan\nDouble-click text: edit\n"
                      "Del: delete selected · Esc: back to Select")
        hint.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(hint)
        root.addStretch(1)

        self.setWidget(body)
        self.setMinimumWidth(240)

    def _refresh_labels(self):
        self.height_label.setText(f"Peak height: {self.height_slider.value() / 100:.2f} mA")
        self.pos_label.setText(f"Peak position: {self.pos_slider.value() / 100:.2f} V")

    def current_graph_params(self):
        return (self.type_combo.currentText(),
                self.height_slider.value() / 100.0,
                self.pos_slider.value() / 100.0)

    def set_graph_params(self, cv_type: str, peak_height: float, peak_position: float):
        idx = self.type_combo.findText(cv_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.height_slider.setValue(int(round(max(0.10, min(2.0, peak_height)) * 100)))
        self.pos_slider.setValue(int(round(max(0.20, min(0.70, peak_position)) * 100)))

    def _emit_update(self):
        self.update_graph_requested.emit(*self.current_graph_params())
