"""Layer manager dock: list of canvas items, selection sync, z-order, locking."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractItemView, QDockWidget, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton, QStyle,
                             QVBoxLayout, QWidget)

from .icons import get_icon


class LayersDock(QDockWidget):
    """Shows items top-most first.  The dock never touches the scene itself; it
    emits signals carrying the affected canvas items and MainWindow wires them
    to CanvasView, which keeps the panel free of canvas knowledge."""

    selection_requested = pyqtSignal(list)      # items to select on the canvas
    move_up_requested = pyqtSignal(list)        # bring forward
    move_down_requested = pyqtSignal(list)      # send backward
    lock_toggle_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__("Layers", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._items: list = []        # parallel to list rows (None = background row)
        self._syncing = False

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setAlternatingRowColors(True)
        self.list.itemSelectionChanged.connect(self._on_list_selection)
        layout.addWidget(self.list, 1)

        self.empty_hint = QLabel("No items yet.\nAdd molecules, text or arrows\nfrom the toolbar.")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet("color:#777;")
        layout.addWidget(self.empty_hint)

        style = self.style()
        row = QHBoxLayout()
        self.btn_up = QPushButton("Up")
        self.btn_up.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.btn_up.setToolTip("Bring selected item(s) forward")
        self.btn_down = QPushButton("Down")
        self.btn_down.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.btn_down.setToolTip("Send selected item(s) backward")
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        layout.addLayout(row)

        self.btn_lock = QPushButton("Lock / Unlock")
        self.btn_lock.setIcon(get_icon("lock"))
        self.btn_lock.setToolTip("Locked items cannot be dragged")
        layout.addWidget(self.btn_lock)

        self.btn_up.clicked.connect(lambda: self.move_up_requested.emit(self._selected_items()))
        self.btn_down.clicked.connect(lambda: self.move_down_requested.emit(self._selected_items()))
        self.btn_lock.clicked.connect(lambda: self.lock_toggle_requested.emit(self._selected_items()))

        self.setWidget(body)
        self.setMinimumWidth(190)
        self._update_buttons()

    # ----------------------------------------------------------------- helpers
    def _selected_items(self) -> list:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        return [self._items[r] for r in rows if self._items[r] is not None]

    def _update_buttons(self):
        has = bool(self._selected_items())
        for b in (self.btn_up, self.btn_down, self.btn_lock):
            b.setEnabled(has)

    def _on_list_selection(self):
        self._update_buttons()
        if self._syncing:
            return
        self.selection_requested.emit(self._selected_items())

    # ------------------------------------------------------------------ public
    def rebuild(self, items_bottom_to_top, background_name=None, selected=()):
        """Repopulate the list. `items_bottom_to_top` is ascending-z order."""
        chosen = {id(i) for i in selected}
        self._syncing = True
        self.list.blockSignals(True)
        self.list.clear()
        self._items = []
        lock_icon = get_icon("lock")
        for item in reversed(list(items_bottom_to_top)):
            row = QListWidgetItem(item.layer_name())
            if getattr(item, "locked", False):
                row.setIcon(lock_icon)
                row.setToolTip("Locked")
            self.list.addItem(row)
            self._items.append(item)
            if id(item) in chosen:
                row.setSelected(True)
        if background_name:
            bg = QListWidgetItem(f"Background: {background_name}")
            bg.setFlags(bg.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            bg.setForeground(Qt.GlobalColor.gray)
            self.list.addItem(bg)
            self._items.append(None)
        self.list.blockSignals(False)
        self._syncing = False
        self.empty_hint.setVisible(not self._items)
        self._update_buttons()

    def select_items(self, items):
        """Mirror a canvas selection into the list (no signals emitted)."""
        chosen = {id(i) for i in items}
        self._syncing = True
        self.list.blockSignals(True)
        for r, obj in enumerate(self._items):
            self.list.item(r).setSelected(obj is not None and id(obj) in chosen)
        self.list.blockSignals(False)
        self._syncing = False
        self._update_buttons()
