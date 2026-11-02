"""Main window: toolbar, vertical splitter (canvas / CV graph), docks, menus."""
from __future__ import annotations

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import (QFileDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                             QSpinBox, QSplitter, QToolBar, QToolButton)

from core import project_manager
from core.image_exporter import stitch_and_export
from .canvas_view import TOOL_ARROW, TOOL_PAN, TOOL_SELECT, CanvasView
from .controls_dock import ControlsDock
from .graph_view import GraphView
from .icons import get_icon
from .items import MOLECULE_TYPES
from .layers_dock import LayersDock
from .library_dock import LibraryDock
from .properties_dock import PropertiesDock

APP_NAME = "Scientific Schematic Editor"
EXPORT_WIDTH = 2400   # px; high-resolution publication output


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1500, 920)
        self._project_path: str | None = None

        self.canvas_view = CanvasView()
        self.graph_view = GraphView()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.canvas_view)
        splitter.addWidget(self.graph_view)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([560, 340])
        self.setCentralWidget(splitter)

        # docks: Layers on the left; Controls above Properties on the right
        self.layers = LayersDock(self)
        self.controls = ControlsDock(self)
        self.properties = PropertiesDock(self)
        self.library = LibraryDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.layers)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.library)
        self.splitDockWidget(self.layers, self.library, Qt.Orientation.Vertical)   # library below layers
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.controls)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties)
        self.splitDockWidget(self.controls, self.properties, Qt.Orientation.Vertical)
        self.resizeDocks([self.layers], [270], Qt.Orientation.Horizontal)
        self.resizeDocks([self.layers, self.library], [260, 420], Qt.Orientation.Vertical)

        self._build_toolbar()
        self._build_menus()
        self._connect_signals()
        self._refresh_layers()
        self._update_title()
        self.statusBar().showMessage(
            "Load a background image, add molecules/text/arrows, then File → Export.")

    # ------------------------------------------------------------- toolbar
    def _make_action(self, text, icon, tip, checkable=False, slot=None):
        act = QAction(get_icon(icon), text, self)
        act.setToolTip(tip)
        act.setStatusTip(tip)
        act.setCheckable(checkable)
        if slot is not None:
            act.triggered.connect(slot)
        return act

    def _build_toolbar(self):
        tb = QToolBar("Tools", self)
        tb.setObjectName("main_toolbar")
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        tb.setMovable(False)
        self.toolbar = tb

        # exclusive interaction tools
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions = {}
        for tool, label, icon, tip in (
                (TOOL_SELECT, "Select", "select", "Select and move items"),
                (TOOL_PAN, "Pan", "pan", "Drag to pan the canvas (middle mouse also pans)"),
                (TOOL_ARROW, "Arrow", "arrow", "Draw arrow: drag on the canvas (Esc to stop)")):
            act = self._make_action(label, icon, tip, checkable=True)
            act.triggered.connect(lambda _=False, t=tool: self.canvas_view.set_tool(t))
            self.tool_group.addAction(act)
            tb.addAction(act)
            self.tool_actions[tool] = act
        self.tool_actions[TOOL_SELECT].setChecked(True)

        tb.addSeparator()

        # Add Molecule: drop-down of molecule types
        self.molecule_button = QToolButton()
        self.molecule_button.setText("Molecule")
        self.molecule_button.setIcon(get_icon("molecule"))
        self.molecule_button.setToolTip("Add a molecule to the canvas")
        self.molecule_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.molecule_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        mol_menu = QMenu(self.molecule_button)
        for kind in MOLECULE_TYPES:
            a = mol_menu.addAction(kind)
            a.triggered.connect(lambda _=False, k=kind: self._add_molecule(k))
        self.molecule_button.setMenu(mol_menu)
        tb.addWidget(self.molecule_button)

        self.act_text = self._make_action("Text", "text", "Add a text label (double-click to edit)",
                                          slot=lambda: self._add_text())
        tb.addAction(self.act_text)

        tb.addSeparator()
        self.act_delete = self._make_action("Delete", "delete", "Delete selected item(s)",
                                            slot=lambda: self.canvas_view.delete_selected())
        tb.addAction(self.act_delete)

        tb.addSeparator()
        self.act_grid = self._make_action("Grid", "grid", "Show / hide alignment grid (Ctrl+G)",
                                          checkable=True)
        self.act_grid.setShortcut("Ctrl+G")
        self.act_snap = self._make_action("Snap", "snap", "Snap dragged items to the grid",
                                          checkable=True)
        self.act_snap.setChecked(True)
        tb.addAction(self.act_grid)
        tb.addAction(self.act_snap)

        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(5, 400)
        self.grid_spin.setValue(self.canvas_view.grid_size)
        self.grid_spin.setSuffix(" px")
        self.grid_spin.setToolTip("Grid spacing (scene pixels)")
        tb.addWidget(self.grid_spin)

        tb.addSeparator()
        self.act_fit = self._make_action("Fit", "fit", "Fit the canvas to the window (Ctrl+0)",
                                         slot=lambda: self.canvas_view.fit_to_scene())
        self.act_fit.setShortcut("Ctrl+0")
        tb.addAction(self.act_fit)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

    # --------------------------------------------------------------- menus
    def _build_menus(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("&File")

        def add(menu, text, slot, shortcut=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            menu.addAction(act)
            return act

        add(file_menu, "New Project", self.new_project, QKeySequence.StandardKey.New)
        self.act_load_project = add(file_menu, "Load Project…", lambda: self.load_project(),
                                    QKeySequence.StandardKey.Open)
        self.act_save_project = add(file_menu, "Save Project", lambda: self.save_project(),
                                    QKeySequence.StandardKey.Save)
        add(file_menu, "Save Project As…", lambda: self.save_project(save_as=True),
            QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        add(file_menu, "Load Background Image…",
            lambda: self.canvas_view.load_background_image(), "Ctrl+B")
        export_menu = file_menu.addMenu("Export")
        add(export_menu, "Export Combined Figure (PNG)…", self.export_combined, "Ctrl+E")
        file_menu.addSeparator()
        add(file_menu, "Quit", self.close, QKeySequence.StandardKey.Quit)

        edit_menu = mb.addMenu("&Edit")
        add(edit_menu, "Delete Selected", lambda: self.canvas_view.delete_selected())
        add(edit_menu, "Clear Canvas", self.clear_canvas)

        view_menu = mb.addMenu("&View")
        view_menu.addAction(self.act_fit)
        view_menu.addAction(self.act_grid)
        view_menu.addAction(self.act_snap)
        view_menu.addSeparator()
        for dock in (self.layers, self.library, self.controls, self.properties):
            view_menu.addAction(dock.toggleViewAction())

    # ------------------------------------------------------------- signals
    def _connect_signals(self):
        cv, sc = self.canvas_view, self.canvas_view.scene()

        # canvas -> docks
        sc.layers_changed.connect(self._refresh_layers)
        sc.selectionChanged.connect(self._on_canvas_selection)
        cv.tool_changed.connect(self._on_tool_changed)

        # layers dock -> canvas  (clicking a layer selects it on the canvas)
        self.layers.selection_requested.connect(cv.select_items)
        self.layers.move_up_requested.connect(lambda items: cv.move_z(items, +1))
        self.layers.move_down_requested.connect(lambda items: cv.move_z(items, -1))
        self.layers.lock_toggle_requested.connect(cv.toggle_lock)

        # component library -> canvas (drag & drop is handled by the canvas itself)
        self.library.component_requested.connect(self._insert_component)
        self.library.background_requested.connect(self._set_background_from_library)

        # grid / snap
        self.act_grid.toggled.connect(cv.set_grid_visible)
        self.act_snap.toggled.connect(cv.set_snap_enabled)
        self.grid_spin.valueChanged.connect(cv.set_grid_size)

        # graph
        self.controls.update_graph_requested.connect(self.graph_view.update_graph)

    def _on_canvas_selection(self):
        # selectionChanged can fire while items are being torn down
        try:
            selected = self.canvas_view.selected_annotation_items()
        except RuntimeError:
            return
        self.layers.select_items(selected)
        self.properties.set_selection(selected)

    def _refresh_layers(self):
        selected = self.canvas_view.selected_annotation_items()
        self.layers.rebuild(self.canvas_view.annotation_items(),
                            self.canvas_view.background_name(), selected)
        self.properties.refresh_values()

    def _on_tool_changed(self, tool: str):
        act = self.tool_actions.get(tool)
        if act is not None and not act.isChecked():
            act.setChecked(True)

    # ------------------------------------------------------------- actions
    def _add_molecule(self, kind: str):
        self.canvas_view.set_tool(TOOL_SELECT)
        self.canvas_view.add_molecule(kind)

    def _insert_component(self, path: str):
        self.canvas_view.set_tool(TOOL_SELECT)
        self.canvas_view.add_component(path)

    def _set_background_from_library(self, path: str):
        if self.canvas_view.load_background_image(path):
            self.statusBar().showMessage(f"Background set: {os.path.basename(path)}", 5000)

    def _add_text(self):
        self.canvas_view.set_tool(TOOL_SELECT)
        self.canvas_view.add_text()

    def clear_canvas(self):
        if self.canvas_view.annotation_items() or self.canvas_view.background_path:
            ans = QMessageBox.question(self, "Clear Canvas",
                                       "Remove the background and all items from the canvas?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.canvas_view.clear_canvas()

    def _update_title(self):
        name = os.path.basename(self._project_path) if self._project_path else "Untitled"
        self.setWindowTitle(f"{name} — {APP_NAME}")

    # ---------------------------------------------------- project save/load
    def collect_project(self) -> dict:
        """Gather the complete editor state into a project dictionary."""
        data = project_manager.new_project()
        data.update(self.canvas_view.to_dict())
        ctype, height, pos = self.graph_view.params
        data["graph"] = {"type": ctype, "peak_height": height, "peak_position": pos}
        return data

    def save_project_to(self, path: str) -> str:
        """Save without any dialogs (raises on failure)."""
        saved = project_manager.save_project(self.collect_project(), path)
        self._project_path = saved
        self._update_title()
        return saved

    def save_project(self, save_as: bool = False) -> bool:
        path = None if save_as else self._project_path
        if not path:
            suggested = self._project_path or "figure.chem"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", suggested, "Chem project (*.chem)")
            if not path:
                return False
        try:
            saved = self.save_project_to(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.statusBar().showMessage(f"Project saved: {saved}", 6000)
        return True

    def open_project_file(self, path: str) -> list[str]:
        """Load without dialogs. Returns warnings; raises ProjectError on failure."""
        data, warnings = project_manager.load_project(path)
        warnings += self.canvas_view.from_dict(data)

        grid = data["grid"]                         # sync toolbar widgets
        self.grid_spin.setValue(grid["size"])
        self.act_snap.setChecked(grid["snap"])
        self.act_grid.setChecked(grid["visible"])

        g = data["graph"]
        self.controls.set_graph_params(g["type"], g["peak_height"], g["peak_position"])
        self.graph_view.update_graph(*self.controls.current_graph_params())

        self.canvas_view.set_tool(TOOL_SELECT)
        self._project_path = os.path.abspath(path)
        self._update_title()
        return warnings

    def load_project(self, path: str | None = None) -> bool:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Project", "", "Chem project (*.chem);;All files (*)")
            if not path:
                return False
        try:
            warnings = self.open_project_file(path)
        except project_manager.ProjectError as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return False
        self.statusBar().showMessage(f"Project loaded: {path}", 6000)
        if warnings:
            QMessageBox.warning(self, "Project loaded with warnings", "\n".join(warnings))
        return True

    def new_project(self):
        if self.canvas_view.annotation_items() or self.canvas_view.background_path:
            ans = QMessageBox.question(self, "New Project",
                                       "Discard the current canvas and start a new project?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.canvas_view.clear_canvas()
        self._project_path = None
        self._update_title()

    # ------------------------------------------------------------- export
    def export_combined(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Combined Figure", "figure.png", "PNG image (*.png)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".png"
        try:
            canvas_img = self.canvas_view.export_to_pil(EXPORT_WIDTH)
            graph_img = self.graph_view.export_to_pil(EXPORT_WIDTH)
            combined = stitch_and_export(canvas_img, graph_img, path, width=EXPORT_WIDTH)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(
            f"Saved {path} ({combined.width}×{combined.height}px)", 8000)
