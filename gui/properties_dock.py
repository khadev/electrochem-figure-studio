"""Context-sensitive properties editor (text / molecule / arrow)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QDockWidget, QDoubleSpinBox,
                             QFontComboBox, QFormLayout, QLabel, QLineEdit,
                             QPushButton, QSlider, QSpinBox, QStackedWidget,
                             QVBoxLayout, QWidget)

from core import asset_library
from .items import ArrowItem, ComponentItem, MoleculeItem, TextItem

PAGE_EMPTY, PAGE_TEXT, PAGE_MOLECULE, PAGE_ARROW, PAGE_COMPONENT = range(5)


def _swatch(button: QPushButton, color: QColor):
    fg = "#000" if color.lightness() > 128 else "#fff"
    button.setText(color.name().upper())
    button.setStyleSheet(f"background-color:{color.name()}; color:{fg}; "
                         "border:1px solid #888; padding:4px;")


class PropertiesDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Properties", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._item = None
        self._updating = False

        self.stack = QStackedWidget()
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color:#777;")
        self.stack.addWidget(self.empty_label)                 # PAGE_EMPTY

        # ---- text page
        text_page = QWidget()
        form = QFormLayout(text_page)
        self.text_edit = QLineEdit()
        self.font_combo = QFontComboBox()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 800)
        self.size_spin.setSuffix(" px")
        self.bold_check = QCheckBox("Bold")
        self.text_color_btn = QPushButton()
        form.addRow("Text", self.text_edit)
        form.addRow("Font", self.font_combo)
        form.addRow("Size", self.size_spin)
        form.addRow("", self.bold_check)
        form.addRow("Color", self.text_color_btn)
        self.stack.addWidget(text_page)                        # PAGE_TEXT

        # ---- molecule page
        mol_page = QWidget()
        mform = QFormLayout(mol_page)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(5, 1500)
        self.scale_label = QLabel()
        self.rot_slider = QSlider(Qt.Orientation.Horizontal)
        self.rot_slider.setRange(-180, 180)
        self.rot_label = QLabel()
        mform.addRow(self.scale_label)
        mform.addRow(self.scale_slider)
        mform.addRow(self.rot_label)
        mform.addRow(self.rot_slider)
        self.stack.addWidget(mol_page)                         # PAGE_MOLECULE

        # ---- arrow page
        arrow_page = QWidget()
        aform = QFormLayout(arrow_page)
        self.arrow_color_btn = QPushButton()
        self.arrow_width_spin = QDoubleSpinBox()
        self.arrow_width_spin.setRange(0.5, 60.0)
        self.arrow_width_spin.setSingleStep(0.5)
        self.arrow_width_spin.setSuffix(" px")
        aform.addRow("Color", self.arrow_color_btn)
        aform.addRow("Thickness", self.arrow_width_spin)
        self.stack.addWidget(arrow_page)                       # PAGE_ARROW

        # ---- component page
        comp_page = QWidget()
        cform = QFormLayout(comp_page)
        self.comp_name_label = QLabel()
        self.comp_name_label.setWordWrap(True)
        self.comp_name_label.setStyleSheet("font-weight:bold;")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_label = QLabel()
        self.comp_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.comp_scale_slider.setRange(1, 800)
        self.comp_scale_label = QLabel()
        self.flip_h_check = QCheckBox("Flip horizontal")
        self.flip_v_check = QCheckBox("Flip vertical")
        cform.addRow(self.comp_name_label)
        cform.addRow(self.opacity_label)
        cform.addRow(self.opacity_slider)
        cform.addRow(self.comp_scale_label)
        cform.addRow(self.comp_scale_slider)
        cform.addRow(self.flip_h_check)
        cform.addRow(self.flip_v_check)
        self.stack.addWidget(comp_page)                        # PAGE_COMPONENT

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.addWidget(self.stack)
        lay.addStretch(1)
        self.setWidget(body)
        self.setMinimumWidth(240)

        # signals
        self.text_edit.textEdited.connect(self._on_text)
        self.font_combo.currentFontChanged.connect(self._on_font_family)
        self.size_spin.valueChanged.connect(self._on_font_size)
        self.bold_check.toggled.connect(self._on_bold)
        self.text_color_btn.clicked.connect(self._choose_text_color)
        self.scale_slider.valueChanged.connect(self._on_scale)
        self.rot_slider.valueChanged.connect(self._on_rotation)
        self.arrow_color_btn.clicked.connect(self._choose_arrow_color)
        self.arrow_width_spin.valueChanged.connect(self._on_arrow_width)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        self.comp_scale_slider.valueChanged.connect(self._on_comp_scale)
        self.flip_h_check.toggled.connect(self._on_flip)
        self.flip_v_check.toggled.connect(self._on_flip)

        self.set_selection([])

    # ----------------------------------------------------------- selection
    def set_selection(self, items):
        items = list(items)
        self._item = None
        if not items:
            self.empty_label.setText("Select an item on the canvas\nto edit its properties.")
            self.stack.setCurrentIndex(PAGE_EMPTY)
        elif len(items) > 1:
            self.empty_label.setText(f"{len(items)} items selected.\nSelect a single item to edit it.")
            self.stack.setCurrentIndex(PAGE_EMPTY)
        else:
            item = items[0]
            self._item = item
            if isinstance(item, TextItem):
                self.stack.setCurrentIndex(PAGE_TEXT)
            elif isinstance(item, MoleculeItem):
                self.stack.setCurrentIndex(PAGE_MOLECULE)
            elif isinstance(item, ArrowItem):
                self.stack.setCurrentIndex(PAGE_ARROW)
            elif isinstance(item, ComponentItem):
                self.stack.setCurrentIndex(PAGE_COMPONENT)
            else:
                self._item = None
                self.stack.setCurrentIndex(PAGE_EMPTY)
        self.refresh_values()

    def refresh_values(self):
        """Pull the current item's values into the widgets (no write-back)."""
        item = self._item
        if item is None:
            return
        self._updating = True
        try:
            if isinstance(item, TextItem):
                if self.text_edit.text() != item.toPlainText():
                    self.text_edit.setText(item.toPlainText())
                f = item.font()
                self.font_combo.setCurrentFont(QFont(f.family()))
                self.size_spin.setValue(f.pixelSize() if f.pixelSize() > 0 else 24)
                self.bold_check.setChecked(f.bold())
                _swatch(self.text_color_btn, item.defaultTextColor())
            elif isinstance(item, MoleculeItem):
                pct = int(round(item.scale() * 100))
                self.scale_slider.setValue(max(5, min(1500, pct)))
                self.scale_label.setText(f"Scale: {pct}%")
                rot = int(round(item.rotation()))
                rot = (rot + 180) % 360 - 180
                self.rot_slider.setValue(rot)
                self.rot_label.setText(f"Rotation: {rot}°")
            elif isinstance(item, ArrowItem):
                _swatch(self.arrow_color_btn, item.color())
                self.arrow_width_spin.setValue(item.width())
            elif isinstance(item, ComponentItem):
                self.comp_name_label.setText(asset_library.display_name(item.source_path)
                                             + ("  (file missing)" if item.missing else ""))
                op = int(round(item.opacity() * 100))
                self.opacity_slider.setValue(op)
                self.opacity_label.setText(f"Opacity: {op}%")
                pct = int(round(item.scale() * 100))
                self.comp_scale_slider.setValue(max(1, min(800, pct)))
                self.comp_scale_label.setText(f"Scale: {pct}%")
                self.flip_h_check.setChecked(item.flip_h)
                self.flip_v_check.setChecked(item.flip_v)
        except RuntimeError:        # underlying C++ item already deleted
            self._item = None
        finally:
            self._updating = False

    # ------------------------------------------------------------ handlers
    def _live(self, cls):
        return self._item if (not self._updating and isinstance(self._item, cls)) else None

    def _on_text(self, text):
        if (item := self._live(TextItem)) is not None:
            item.setPlainText(text)
            item.refresh_origin()

    def _on_font_family(self, font: QFont):
        if (item := self._live(TextItem)) is not None:
            f = item.font()
            f.setFamily(font.family())
            item.setFont(f)
            item.refresh_origin()

    def _on_font_size(self, value):
        if (item := self._live(TextItem)) is not None:
            f = item.font()
            f.setPixelSize(int(value))
            item.setFont(f)
            item.refresh_origin()

    def _on_bold(self, checked):
        if (item := self._live(TextItem)) is not None:
            f = item.font()
            f.setBold(bool(checked))
            item.setFont(f)
            item.refresh_origin()

    def _apply_text_color(self, color: QColor):
        if (item := self._live(TextItem)) is not None and color.isValid():
            item.setDefaultTextColor(color)
            _swatch(self.text_color_btn, color)

    def _choose_text_color(self):
        if isinstance(self._item, TextItem):
            color = QColorDialog.getColor(self._item.defaultTextColor(), self, "Text color")
            if color.isValid():
                self._apply_text_color(color)

    def _on_scale(self, value):
        if (item := self._live(MoleculeItem)) is not None:
            item.setScale(value / 100.0)
            self.scale_label.setText(f"Scale: {value}%")

    def _on_rotation(self, value):
        if (item := self._live(MoleculeItem)) is not None:
            item.setRotation(float(value))
            self.rot_label.setText(f"Rotation: {value}°")

    def _apply_arrow_color(self, color: QColor):
        if (item := self._live(ArrowItem)) is not None and color.isValid():
            item.set_color(color)
            _swatch(self.arrow_color_btn, color)

    def _choose_arrow_color(self):
        if isinstance(self._item, ArrowItem):
            color = QColorDialog.getColor(self._item.color(), self, "Arrow color")
            if color.isValid():
                self._apply_arrow_color(color)

    def _on_arrow_width(self, value):
        if (item := self._live(ArrowItem)) is not None:
            item.set_width(value)

    # ---- component handlers
    def _on_opacity(self, value):
        if (item := self._live(ComponentItem)) is not None:
            item.setOpacity(value / 100.0)
            self.opacity_label.setText(f"Opacity: {value}%")

    def _on_comp_scale(self, value):
        if (item := self._live(ComponentItem)) is not None:
            item.setScale(max(1, value) / 100.0)
            self.comp_scale_label.setText(f"Scale: {value}%")

    def _on_flip(self, _checked=False):
        if (item := self._live(ComponentItem)) is not None:
            item.set_flip(self.flip_h_check.isChecked(), self.flip_v_check.isChecked())
