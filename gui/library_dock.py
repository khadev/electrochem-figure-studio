"""Component Library dock: thumbnail browser for assets/components and assets/backgrounds.

* Scans the asset folders (recursively) for PNG/JPG files and shows thumbnails
  in an icon-mode list (transparent images are previewed on a checkerboard).
* Search box filters by name; a category switch toggles Components/Backgrounds.
* Drag a thumbnail onto the canvas, or double-click / press "Insert".
* A file-system watcher keeps the list in sync when files are added or removed.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PyQt6.QtCore import (QFileSystemWatcher, QMimeData, QSize, Qt, QTimer, QUrl,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QDesktopServices, QDrag, QIcon, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDockWidget, QFileDialog,
                             QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from core import asset_library as al

THUMB = 88
PATH_ROLE = Qt.ItemDataRole.UserRole
KIND_ROLE = Qt.ItemDataRole.UserRole + 1


def make_thumbnail(path: str):
    """Return (QIcon, (w, h)) for an image, or (None, None) if unreadable.
    Transparent areas are drawn over a light checkerboard."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    original = (size.width(), size.height()) if size.isValid() else None
    if size.isValid():
        size.scale(THUMB, THUMB, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
    img = reader.read()
    if img.isNull():
        return None, None
    pm = QPixmap(THUMB, THUMB)
    p = QPainter(pm)
    for y in range(0, THUMB, 8):
        for x in range(0, THUMB, 8):
            p.fillRect(x, y, 8, 8, QColor("#ffffff") if (x // 8 + y // 8) % 2 == 0
                       else QColor("#e3e6ea"))
    p.drawImage((THUMB - img.width()) // 2, (THUMB - img.height()) // 2, img)
    p.setPen(QColor("#b4bac2"))
    p.drawRect(0, 0, THUMB - 1, THUMB - 1)
    p.end()
    return QIcon(pm), original or (img.width(), img.height())


class AssetList(QListWidget):
    """Icon-mode list whose items can be dragged out as ASSET_MIME payloads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 26, THUMB + 44))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setWordWrap(True)
        self.setSpacing(2)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def mimeTypes(self):
        return [al.ASSET_MIME]

    def mimeData(self, items):
        mime = QMimeData()
        mime.setData(al.ASSET_MIME, al.encode_assets(
            [(it.data(KIND_ROLE), it.data(PATH_ROLE)) for it in items]))
        mime.setUrls([QUrl.fromLocalFile(it.data(PATH_ROLE)) for it in items])
        return mime

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData(items))
        pm = items[0].icon().pixmap(THUMB, THUMB)
        drag.setPixmap(pm)
        drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.DropAction.CopyAction)


class LibraryDock(QDockWidget):
    component_requested = pyqtSignal(str)     # insert this image at the canvas centre
    background_requested = pyqtSignal(str)    # use this image as the canvas background

    CATEGORIES = (("Components", al.KIND_COMPONENT), ("Backgrounds", al.KIND_BACKGROUND))

    def __init__(self, parent=None, components_dir=None, backgrounds_dir=None):
        super().__init__("Component Library", parent)
        self.setObjectName("component_library_dock")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                             Qt.DockWidgetArea.RightDockWidgetArea)
        self._dirs = {al.KIND_COMPONENT: Path(components_dir or al.COMPONENTS_DIR),
                      al.KIND_BACKGROUND: Path(backgrounds_dir or al.BACKGROUNDS_DIR)}
        for folder in self._dirs.values():
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        self._thumb_cache: dict = {}

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(6, 6, 6, 6)

        self.category = QComboBox()
        for label, kind in self.CATEGORIES:
            self.category.addItem(label, kind)
        lay.addWidget(self.category)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name…")
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)

        self.list = AssetList()
        lay.addWidget(self.list, 1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.btn_insert = QPushButton("Insert")
        self.btn_insert.setToolTip("Insert the selected item(s) (or double-click / drag onto the canvas)")
        self.btn_add = QPushButton("Add…")
        self.btn_add.setToolTip("Copy image files into this library folder")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_folder = QPushButton("Folder")
        self.btn_folder.setToolTip("Open the library folder in your file manager")
        for b in (self.btn_insert, self.btn_add, self.btn_refresh, self.btn_folder):
            row.addWidget(b)
        lay.addLayout(row)
        self.setWidget(body)
        self.setMinimumWidth(230)

        self.category.currentIndexChanged.connect(lambda _: self.refresh())
        self.search.textChanged.connect(self._apply_filter)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.itemSelectionChanged.connect(self._update_buttons)
        self.btn_insert.clicked.connect(self.insert_selected)
        self.btn_add.clicked.connect(self.add_files)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_folder.clicked.connect(self.open_folder)

        # live folder watching (debounced)
        self._watcher = QFileSystemWatcher(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self.refresh)
        self._watcher.directoryChanged.connect(lambda _: self._timer.start())
        self._watcher.fileChanged.connect(lambda _: self._timer.start())

        self.refresh()

    # -------------------------------------------------------------- state
    @property
    def current_kind(self) -> str:
        return self.category.currentData()

    def folder_for(self, kind: str) -> Path:
        return self._dirs[kind]

    def set_category(self, kind: str):
        idx = self.category.findData(kind)
        if idx >= 0:
            self.category.setCurrentIndex(idx)

    def visible_names(self) -> list[str]:
        return [self.list.item(i).text() for i in range(self.list.count())
                if not self.list.item(i).isHidden()]

    # ------------------------------------------------------------ scanning
    def _thumbnail(self, path: str):
        try:
            st = os.stat(path)
            key = (path, st.st_mtime_ns, st.st_size)
        except OSError:
            return None, None
        if key not in self._thumb_cache:
            self._thumb_cache[key] = make_thumbnail(path)
        return self._thumb_cache[key]

    def refresh(self):
        """Re-scan the current category's folder and rebuild the thumbnails."""
        kind = self.current_kind
        folder = self._dirs[kind]
        keep = {self.list.item(i).data(PATH_ROLE) for i in range(self.list.count())
                if self.list.item(i).isSelected()}
        self.list.blockSignals(True)
        self.list.clear()
        for name, path in al.scan_folder(folder):
            icon, dims = self._thumbnail(path)
            if icon is None:                      # unreadable / corrupt image
                continue
            item = QListWidgetItem(icon, name)
            item.setData(PATH_ROLE, path)
            item.setData(KIND_ROLE, kind)
            item.setToolTip(f"{os.path.basename(path)}\n{dims[0]} × {dims[1]} px\n{path}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setSizeHint(QSize(THUMB + 20, THUMB + 40))
            self.list.addItem(item)
            if path in keep:
                item.setSelected(True)
        self.list.blockSignals(False)

        self._rewatch(folder)
        self._apply_filter()
        self._update_buttons()

    def _rewatch(self, folder: Path):
        old = self._watcher.directories() + self._watcher.files()
        if old:
            self._watcher.removePaths(old)
        if not folder.is_dir():
            return
        paths = [str(folder)]
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            paths += [os.path.join(root, d) for d in dirs]
            paths += [os.path.join(root, f) for f in files if al.is_image_file(f)]
        self._watcher.addPaths(paths[:400])       # keep OS watch handles bounded

    def _apply_filter(self):
        text = self.search.text().strip().lower()
        shown = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            hit = (not text) or text in item.text().lower() \
                or text in os.path.basename(item.data(PATH_ROLE)).lower()
            item.setHidden(not hit)
            shown += hit
        total = self.list.count()
        if total == 0:
            self.status.setText(f"No images found. Drop PNG/JPG files into:\n{self.folder_for(self.current_kind)}")
        elif shown == 0:
            self.status.setText(f"No match for “{self.search.text().strip()}” ({total} available).")
        else:
            self.status.setText(f"{shown} of {total} · double-click or drag onto the canvas")
        self._update_buttons()

    def _update_buttons(self):
        self.btn_insert.setEnabled(bool(self._selected_entries()))

    # ------------------------------------------------------------- actions
    def _selected_entries(self) -> list[tuple[str, str]]:
        return [(it.data(KIND_ROLE), it.data(PATH_ROLE)) for it in self.list.selectedItems()
                if not it.isHidden()]

    def _emit(self, kind: str, path: str):
        (self.background_requested if kind == al.KIND_BACKGROUND
         else self.component_requested).emit(path)

    def _on_double_click(self, item: QListWidgetItem):
        self._emit(item.data(KIND_ROLE), item.data(PATH_ROLE))

    def insert_selected(self):
        for kind, path in self._selected_entries():
            self._emit(kind, path)

    def add_files(self, paths=None):
        """Copy image files into the current category folder (never overwrites)."""
        if paths is None:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Add images to the library", "",
                "Images (*.png *.jpg *.jpeg);;All files (*)")
        copied = []
        for src in paths or []:
            if not al.is_image_file(src):
                continue
            dest = al.unique_destination(self.folder_for(self.current_kind), os.path.basename(src))
            try:
                shutil.copy2(src, dest)
                copied.append(dest)
            except OSError:
                continue
        self.refresh()
        for i in range(self.list.count()):
            self.list.item(i).setSelected(self.list.item(i).data(PATH_ROLE) in
                                          [os.path.abspath(c) for c in copied])
        return copied

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.folder_for(self.current_kind))))
