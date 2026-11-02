"""Headless feature tests.  Run:  python tests/test_features.py   (or pytest)."""
import json
import os
import shutil
import sys
import tempfile
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_API", "pyqt6")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, QUrl, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from core import asset_library as al  # noqa: E402
from core import project_manager as pm  # noqa: E402
from gui.items import ArrowItem, ComponentItem, MoleculeItem, TextItem, MOLECULE_TYPES  # noqa: E402
from gui.library_dock import LibraryDock  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402

TMP = tempfile.mkdtemp(prefix="chem_test_")


_WINDOWS = []          # keep windows alive: avoids teardown noise from pending matplotlib redraws


def first_visible(lib):
    return next(lib.list.item(i) for i in range(lib.list.count()) if not lib.list.item(i).isHidden())


def make_window(bg=True):
    w = MainWindow()
    _WINDOWS.append(w)
    w.show()
    app.processEvents()
    if bg:
        path = os.path.join(TMP, "bg.png")
        if not os.path.exists(path):
            Image.new("RGB", (1000, 700), (90, 150, 90)).save(path)
        assert w.canvas_view.load_background_image(path)
    app.processEvents()
    return w


def rows(w):
    return [w.layers.list.item(i).text() for i in range(w.layers.list.count())]


def view_pos(w, scene_pt):
    return w.canvas_view.mapFromScene(scene_pt)


def drag(w, start_scene, end_scene, steps=6):
    v = w.canvas_view.viewport()
    a, b = view_pos(w, start_scene), view_pos(w, end_scene)
    QTest.mousePress(v, Qt.MouseButton.LeftButton, pos=a)
    for k in range(1, steps + 1):
        p = QPoint(a.x() + (b.x() - a.x()) * k // steps, a.y() + (b.y() - a.y()) * k // steps)
        QTest.mouseMove(v, p)
        app.processEvents()
    QTest.mouseRelease(v, Qt.MouseButton.LeftButton, pos=b)
    app.processEvents()


def center_of(item):
    return item.mapToScene(item.boundingRect().center())


# ------------------------------------------------------------------ tests
def test_toolbar_has_all_tools():
    w = make_window()
    labels = [a.text() for a in w.toolbar.actions() if a.text()]
    for needed in ("Select", "Pan", "Arrow", "Text", "Delete"):
        assert needed in labels, (needed, labels)
    assert w.molecule_button.menu() is not None
    assert len(w.molecule_button.menu().actions()) == len(MOLECULE_TYPES)
    # old canvas buttons are gone from the controls dock
    assert not hasattr(w.controls, "mol_combo")


def test_add_items_and_layer_list():
    w = make_window()
    cv = w.canvas_view
    w.molecule_button.menu().actions()[0].trigger()
    w.act_text.trigger()
    cv.add_arrow(QPointF(100, 100), QPointF(300, 200))
    app.processEvents()
    r = rows(w)
    assert r[0] == "Arrow" and r[1].startswith("Text:") and r[2] == "Methanol", r
    assert r[-1].startswith("Background:"), r


def test_layer_click_selects_on_canvas_and_back():
    w = make_window()
    cv = w.canvas_view
    m = cv.add_molecule(MOLECULE_TYPES[1])
    t = cv.add_text("NiMoO4")
    app.processEvents()
    assert rows(w)[0] == "Text: NiMoO4"
    # list -> canvas
    w.layers.list.clearSelection()
    w.layers.list.item(1).setSelected(True)        # the molecule row
    app.processEvents()
    assert m.isSelected() and not t.isSelected()
    # properties followed the selection
    assert w.properties.stack.currentIndex() == 2
    # canvas -> list
    cv.scene().clearSelection()
    t.setSelected(True)
    app.processEvents()
    sel = [w.layers.list.row(i) for i in w.layers.list.selectedItems()]
    assert sel == [0], sel
    assert w.properties.stack.currentIndex() == 1
    # multi-select from the list
    w.layers.list.item(0).setSelected(True)
    w.layers.list.item(1).setSelected(True)
    app.processEvents()
    assert m.isSelected() and t.isSelected()
    assert "2 items" in w.properties.empty_label.text()


def test_z_order_buttons():
    w = make_window()
    cv = w.canvas_view
    a = cv.add_molecule(MOLECULE_TYPES[0])
    b = cv.add_text("B")
    c = cv.add_molecule(MOLECULE_TYPES[2])
    assert cv.annotation_items() == [a, b, c]
    assert a.zValue() < b.zValue() < c.zValue()
    w.layers.list.clearSelection()
    w.layers.list.item(2).setSelected(True)         # bottom-most row = a
    app.processEvents()
    w.layers.btn_up.click()
    assert cv.annotation_items() == [b, a, c], cv.annotation_items()
    assert a.zValue() > b.zValue()
    assert rows(w)[:3] == ["Hydrogen", "Methanol", "Text: B"], rows(w)
    assert a.isSelected()                           # selection kept after rebuild
    w.layers.btn_down.click()
    w.layers.btn_down.click()                       # already at bottom: no-op
    assert cv.annotation_items() == [a, b, c]
    # top item can't go higher
    w.layers.list.clearSelection()
    w.layers.list.item(0).setSelected(True)
    w.layers.btn_up.click()
    assert cv.annotation_items() == [a, b, c]


def test_lock_prevents_moving():
    w = make_window()
    cv = w.canvas_view
    m = cv.add_molecule(MOLECULE_TYPES[0])
    m.setPos(300, 300)
    app.processEvents()
    w.layers.list.clearSelection()
    w.layers.list.item(0).setSelected(True)
    w.layers.btn_lock.click()
    assert m.locked and not (m.flags() & m.GraphicsItemFlag.ItemIsMovable)
    assert not w.layers.list.item(0).icon().isNull()           # lock icon shown
    before = QPointF(m.pos())
    drag(w, center_of(m), center_of(m) + QPointF(120, 60))
    assert m.pos() == before, (m.pos(), before)
    w.layers.btn_lock.click()                                  # unlock
    assert not m.locked
    drag(w, center_of(m), center_of(m) + QPointF(120, 60))
    assert m.pos() != before


def test_properties_text():
    w = make_window()
    t = w.canvas_view.add_text("Hello")
    app.processEvents()
    p = w.properties
    assert p.stack.currentIndex() == 1 and p.text_edit.text() == "Hello"
    QTest.keyClicks(p.text_edit, " World")
    assert t.toPlainText() == "Hello World"
    assert rows(w)[0] == "Text: Hello World"                   # layer name follows
    p.font_combo.setCurrentFont(QFont("Courier New"))
    assert t.font().family() == QFont("Courier New").family() or \
        t.font().family() == p.font_combo.currentFont().family()
    p.size_spin.setValue(47)
    assert t.font().pixelSize() == 47
    p.bold_check.setChecked(False)
    assert not t.font().bold()
    p._apply_text_color(QColor("#00aa00"))
    assert t.defaultTextColor().name() == "#00aa00"


def test_properties_molecule_and_arrow():
    w = make_window()
    m = w.canvas_view.add_molecule(MOLECULE_TYPES[0])
    app.processEvents()
    p = w.properties
    assert p.stack.currentIndex() == 2
    p.scale_slider.setValue(300)
    assert abs(m.scale() - 3.0) < 1e-9
    p.rot_slider.setValue(45)
    assert abs(m.rotation() - 45) < 1e-9
    a = w.canvas_view.add_arrow(QPointF(50, 50), QPointF(250, 120))
    app.processEvents()
    assert p.stack.currentIndex() == 3
    p._apply_arrow_color(QColor("#ff0000"))
    assert a.color().name() == "#ff0000"
    p.arrow_width_spin.setValue(9.0)
    assert a.width() == 9.0
    # nothing selected -> empty page
    w.canvas_view.scene().clearSelection()
    app.processEvents()
    assert p.stack.currentIndex() == 0


def test_grid_toggle_and_snapping_with_mouse():
    w = make_window()
    cv = w.canvas_view
    m = cv.add_molecule(MOLECULE_TYPES[1])
    m.setPos(207, 233)
    app.processEvents()
    # grid off: free movement
    drag(w, center_of(m), center_of(m) + QPointF(37, 29))
    c = center_of(m)
    assert not (abs(c.x() / 50 - round(c.x() / 50)) < 1e-6 and
                abs(c.y() / 50 - round(c.y() / 50)) < 1e-6)
    # grid on + spacing 50 -> centre snaps to the nearest grid intersection
    w.grid_spin.setValue(50)
    w.act_grid.setChecked(True)
    assert cv.grid_visible and cv.grid_size == 50
    drag(w, center_of(m), center_of(m) + QPointF(61, 44))
    c = center_of(m)
    assert abs(c.x() % 50) < 1e-6 or abs(c.x() % 50 - 50) < 1e-6, c
    assert abs(c.y() % 50) < 1e-6 or abs(c.y() % 50 - 50) < 1e-6, c
    # snap toggle off -> free again
    w.act_snap.setChecked(False)
    drag(w, center_of(m), center_of(m) + QPointF(13, 7))
    c = center_of(m)
    assert not (abs(c.x() % 50) < 1e-6 and abs(c.y() % 50) < 1e-6)
    # text snaps as well
    w.act_snap.setChecked(True)
    t = cv.add_text("snap")
    t.setPos(333, 111)
    drag(w, center_of(t), center_of(t) + QPointF(23, 31))
    c = center_of(t)
    assert abs(c.x() % 50) < 1e-6 or abs(c.x() % 50 - 50) < 1e-6, c


def test_arrow_tool_draw_snap_and_escape():
    w = make_window()
    cv = w.canvas_view
    w.grid_spin.setValue(40)
    w.act_grid.setChecked(True)
    w.tool_actions["arrow"].trigger()
    assert cv.tool == "arrow" and w.tool_actions["arrow"].isChecked()
    drag(w, QPointF(103, 117), QPointF(405, 298))
    arrows = [i for i in cv.annotation_items() if isinstance(i, ArrowItem)]
    assert len(arrows) == 1
    ln = arrows[0].line()
    for v in (ln.x1(), ln.y1(), ln.x2(), ln.y2()):
        assert abs(v / 40 - round(v / 40)) < 1e-6, v        # both ends on the grid
    QTest.keyClick(cv, Qt.Key.Key_Escape)
    assert cv.tool == "select" and w.tool_actions["select"].isChecked()
    # pan tool does not move items
    m = cv.add_molecule(MOLECULE_TYPES[0])
    before = QPointF(m.pos())
    w.tool_actions["pan"].trigger()
    assert cv.tool == "pan"
    drag(w, center_of(m), center_of(m) + QPointF(80, 40))
    assert m.pos() == before


def test_delete_key_and_button():
    w = make_window()
    cv = w.canvas_view
    cv.add_molecule(MOLECULE_TYPES[0])
    cv.add_text("x")
    app.processEvents()
    QTest.keyClick(cv, Qt.Key.Key_Delete)
    assert len(cv.annotation_items()) == 1            # only the selected text was removed
    w.act_delete.trigger()                            # nothing selected -> no-op
    assert len(cv.annotation_items()) == 1
    cv.annotation_items()[0].setSelected(True)
    w.act_delete.trigger()
    assert not cv.annotation_items()
    assert rows(w) == ["Background: bg.png"], rows(w)


def test_save_load_roundtrip_and_relocation():
    w = make_window()
    cv = w.canvas_view
    m = cv.add_molecule(MOLECULE_TYPES[0])
    m.setPos(321.5, 120.25)
    m.setScale(2.75)
    m.setRotation(30)
    t = cv.add_text("NiMoO₄ nanorods")
    t.setPos(50, 600)
    f = t.font(); f.setFamily("Courier New"); f.setPixelSize(33); f.setBold(False); f.setItalic(True)
    t.setFont(f)
    t.setDefaultTextColor(QColor("#123456"))
    a = cv.add_arrow(QPointF(10, 20), QPointF(210, 220))
    a.set_color(QColor("#ab1234")); a.set_width(7.0); a.setPos(5, 6)
    c = cv.add_molecule(MOLECULE_TYPES[2])
    cv.move_z([m], +1)                       # change stacking order
    cv.set_locked([t], True)
    w.grid_spin.setValue(35); w.act_snap.setChecked(False); w.act_grid.setChecked(True)
    w.controls.set_graph_params("Catalytic Wave", 1.2, 0.35)
    w.controls.update_btn.click()
    app.processEvents()

    proj_dir = os.path.join(TMP, "proj"); os.makedirs(proj_dir, exist_ok=True)
    shutil.copy(os.path.join(TMP, "bg.png"), os.path.join(proj_dir, "bg.png"))
    cv._set_background(os.path.join(proj_dir, "bg.png"))
    path = os.path.join(proj_dir, "demo")           # extension added automatically
    saved = w.save_project_to(path)
    assert saved.endswith(".chem") and os.path.isfile(saved)
    raw = json.load(open(saved, encoding="utf-8"))
    assert raw["format"] == "chem-project"
    assert raw["background"]["path"] == "bg.png", raw["background"]       # relative
    assert len(raw["molecules"]) == 2 and len(raw["texts"]) == 1 and len(raw["arrows"]) == 1
    assert "NiMoO₄ nanorods" in open(saved, encoding="utf-8").read()
    before = cv.to_dict()
    names_before = rows(w)

    def check(win):
        after = win.canvas_view.to_dict()
        assert after["canvas"] == before["canvas"]
        assert after["grid"] == {"visible": True, "size": 35, "snap": False}, after["grid"]
        for key in ("molecules", "texts", "arrows"):
            assert len(after[key]) == len(before[key]), key
            for x, y in zip(sorted(after[key], key=lambda d: d["z"]),
                            sorted(before[key], key=lambda d: d["z"])):
                for k, v in y.items():
                    if isinstance(v, float):
                        assert abs(x[k] - v) < 1e-6, (key, k, x[k], v)
                    else:
                        assert x[k] == v, (key, k, x[k], v)
        # relative stacking preserved
        order_b = [type(i).__name__ + i.layer_name() for i in cv.annotation_items()]
        order_a = [type(i).__name__ + i.layer_name() for i in win.canvas_view.annotation_items()]
        assert order_a == order_b, (order_a, order_b)
        assert rows(win) == names_before
        assert win.controls.current_graph_params() == ("Catalytic Wave", 1.2, 0.35)
        assert win.graph_view.params == ("Catalytic Wave", 1.2, 0.35)
        locked = [i for i in win.canvas_view.annotation_items() if i.locked]
        assert len(locked) == 1 and isinstance(locked[0], TextItem)
        assert not (locked[0].flags() & locked[0].GraphicsItemFlag.ItemIsMovable)

    w2 = make_window(bg=False)
    warnings = w2.open_project_file(saved)
    assert warnings == [], warnings
    assert w2.canvas_view.background_path.endswith("bg.png")
    assert w2.windowTitle().startswith("demo.chem")
    check(w2)
    # rendering of both scenes must match pixel-for-pixel
    img1 = cv.export_to_pil(800); img2 = w2.canvas_view.export_to_pil(800)
    assert img1.tobytes() == img2.tobytes(), "re-loaded scene renders differently"

    # move the whole project folder: relative path still resolves
    moved = os.path.join(TMP, "moved"); shutil.copytree(proj_dir, moved, dirs_exist_ok=True)
    shutil.rmtree(proj_dir)
    w3 = make_window(bg=False)
    assert w3.open_project_file(os.path.join(moved, "demo.chem")) == []
    assert os.path.dirname(w3.canvas_view.background_path) == os.path.abspath(moved)
    check(w3)

    # delete the image: loads with a warning, layout/items intact
    os.remove(os.path.join(moved, "bg.png"))
    w4 = make_window(bg=False)
    warn = w4.open_project_file(os.path.join(moved, "demo.chem"))
    assert any("Background image not found" in x for x in warn), warn
    assert len(w4.canvas_view.annotation_items()) == 4
    assert w4.canvas_view.sceneRect().width() == 1000


def test_corrupt_and_foreign_files():
    bad = os.path.join(TMP, "bad.chem")
    open(bad, "w").write("{not json")
    for content, exc in (("{not json", pm.ProjectError), ('{"hello": 1}', pm.ProjectError)):
        open(bad, "w").write(content)
        try:
            pm.load_project(bad)
        except pm.ProjectError:
            pass
        else:
            raise AssertionError("expected ProjectError")
    # partially damaged file still opens, bad entries are skipped
    open(bad, "w").write(json.dumps({"format": "chem-project", "version": 1,
                                     "molecules": [{"kind": "Methanol (CH₃OH)", "x": 1, "y": 2},
                                                   {"x": 5}, {"kind": "Unobtainium", "x": 0, "y": 0}],
                                     "arrows": [{"x1": 0}], "texts": [{"text": "ok"}]}))
    w = make_window(bg=False)
    warnings = w.open_project_file(bad)
    assert len(w.canvas_view.annotation_items()) == 2          # methanol + text
    assert any("Unobtainium" in x for x in warnings) and any("arrow" in x for x in warnings)


def test_export_has_no_grid_or_selection_and_still_works():
    w = make_window(bg=False)
    w.act_grid.setChecked(True)
    img = w.canvas_view.export_to_pil(600)
    assert img.getextrema() == ((255, 255), (255, 255), (255, 255)), "grid leaked into export"
    m = w.canvas_view.add_molecule(MOLECULE_TYPES[0])
    assert m.isSelected()
    out = os.path.join(TMP, "combined.png")
    from core.image_exporter import stitch_and_export
    comb = stitch_and_export(w.canvas_view.export_to_pil(1200),
                             w.graph_view.export_to_pil(1200), out, width=1200)
    assert os.path.isfile(out) and comb.width == 1200
    assert m.isSelected()                                      # selection restored


def test_new_project_resets():
    w = make_window()
    w.canvas_view.add_text("x")
    w.canvas_view.clear_canvas()
    assert not w.canvas_view.annotation_items() and w.canvas_view.background_path is None
    assert rows(w) == []
    assert w.layers.empty_hint.isVisibleTo(w)


def test_ui_screenshot():
    w = make_window()
    w.resize(1500, 920)
    cv = w.canvas_view
    cv.add_molecule(MOLECULE_TYPES[0]).setPos(200, 120)
    cv.add_molecule(MOLECULE_TYPES[1]).setPos(560, 160)
    cv.add_text("NiMoO₄ nanorods").setPos(120, 450)
    cv.add_arrow(QPointF(300, 200), QPointF(520, 330))
    for name, at in (("nickel foam", QPointF(300, 520)), ("ppy coated rod", QPointF(420, 330)),
                     ("nimoo4 nanorod", QPointF(330, 330)), ("reaction arrow green", QPointF(760, 330))):
        w.library.search.setText(name.split()[0])
        match = [i for i in range(w.library.list.count()) if w.library.list.item(i).text() == name]
        cv.add_component(w.library.list.item(match[0]).data(Qt.ItemDataRole.UserRole), at=at)
    w.library.search.clear()
    w.act_grid.setChecked(False)
    w.layers.list.item(1).setSelected(True)
    app.processEvents()
    w.grab().save("/tmp/ui_screenshot.png")


# ======================================================= component library
def make_asset(path, size=(200, 120)):
    """Transparent 10px border, left half red, right half blue (asymmetric on purpose)."""
    from PIL import ImageDraw
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, w // 2 - 1, h - 11], fill=(255, 0, 0, 255))
    d.rectangle([w // 2, 10, w - 11, h - 11], fill=(0, 0, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    return path


def px(w, x, y):
    return w.canvas_view.export_to_pil(1200).getpixel((x, y))


def asset_mime(entries):
    mime = QMimeData()
    mime.setData(al.ASSET_MIME, al.encode_assets(entries))
    return mime


def send_drop(w, mime, scene_pt):
    """Send a real DragEnter + Drop through the viewport (exercises Qt event routing)."""
    vp = w.canvas_view.viewport()
    pos = w.canvas_view.mapFromScene(scene_pt)
    enter = QDragEnterEvent(pos, Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, enter)
    drop = QDropEvent(QPointF(pos), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, drop)
    app.processEvents()
    return enter.isAccepted(), drop.isAccepted()


def components(w):
    return [i for i in w.canvas_view.annotation_items() if isinstance(i, ComponentItem)]


def test_component_item_basics_and_properties():
    w = make_window(bg=False)
    cv = w.canvas_view
    path = make_asset(os.path.join(TMP, "lib1", "red_blue.png"))
    item = cv.add_component(path, at=QPointF(600, 400))
    item.setScale(1.0)
    app.processEvents()
    F = item.GraphicsItemFlag
    assert isinstance(item, ComponentItem)
    assert item.flags() & F.ItemIsMovable and item.flags() & F.ItemIsSelectable
    assert item.layer_name() == "Component: red blue", item.layer_name()
    assert rows(w)[0] == "Component: red blue"
    c0 = center_of(item)
    assert abs(c0.x() - 600) < 0.6 and abs(c0.y() - 400) < 0.6, c0
    assert px(w, 550, 400) == (255, 0, 0) and px(w, 650, 400) == (0, 0, 255)

    p = w.properties
    assert p.stack.currentIndex() == 4                          # component page
    p.refresh_values()                                          # item.setScale() above bypassed the panel
    assert p.comp_scale_slider.value() == 100
    p.opacity_slider.setValue(50)
    assert abs(item.opacity() - 0.5) < 1e-9
    r, g, b = px(w, 550, 400)
    assert r == 255 and abs(g - 128) <= 2 and abs(b - 128) <= 2, (r, g, b)   # blended with white
    p.opacity_slider.setValue(100)
    p.comp_scale_slider.setValue(150)
    assert abs(item.scale() - 1.5) < 1e-9
    p.comp_scale_slider.setValue(100)

    p.flip_h_check.setChecked(True)                             # mirror left <-> right
    assert item.flip_h and not item.flip_v and item.transform().m11() == -1
    assert px(w, 550, 400) == (0, 0, 255) and px(w, 650, 400) == (255, 0, 0)
    c1 = center_of(item)
    assert abs(c1.x() - c0.x()) < 1e-6 and abs(c1.y() - c0.y()) < 1e-6   # centre fixed
    p.flip_v_check.setChecked(True)
    assert item.flip_v and item.transform().m22() == -1
    p.flip_h_check.setChecked(False); p.flip_v_check.setChecked(False)
    assert px(w, 550, 400) == (255, 0, 0)

    # selecting another item type switches the page and back again
    cv.add_text("t")
    app.processEvents()
    assert p.stack.currentIndex() == 1
    cv.scene().clearSelection(); item.setSelected(True); app.processEvents()
    assert p.stack.currentIndex() == 4 and p.opacity_slider.value() == 100


def test_component_lock_zorder_and_snapping():
    w = make_window(bg=False)
    cv = w.canvas_view
    path = make_asset(os.path.join(TMP, "lib1", "red_blue.png"))
    comp = cv.add_component(path, at=QPointF(500, 300))
    mol = cv.add_molecule(MOLECULE_TYPES[0])
    mol.setPos(700, 500)
    assert cv.annotation_items() == [comp, mol]
    # z-order through the layer manager
    w.layers.list.clearSelection()
    w.layers.list.item(1).setSelected(True)            # bottom row = component
    w.layers.btn_up.click()
    assert cv.annotation_items() == [mol, comp] and comp.zValue() > mol.zValue()
    # lock
    w.layers.btn_lock.click()
    assert comp.locked and not (comp.flags() & comp.GraphicsItemFlag.ItemIsMovable)
    before = QPointF(comp.pos())
    drag(w, center_of(comp), center_of(comp) + QPointF(90, 40))
    assert comp.pos() == before
    w.layers.btn_lock.click()
    assert not comp.locked
    # snapping while dragging (grid 50)
    w.grid_spin.setValue(50)
    w.act_grid.setChecked(True)
    comp.setSelected(True)
    drag(w, center_of(comp), center_of(comp) + QPointF(61, 44))
    c = center_of(comp)
    assert min(c.x() % 50, 50 - c.x() % 50) < 1e-6 and min(c.y() % 50, 50 - c.y() % 50) < 1e-6, c
    w.act_snap.setChecked(False)
    drag(w, center_of(comp), center_of(comp) + QPointF(13, 7))
    c = center_of(comp)
    assert not (c.x() % 50 < 1e-6 and c.y() % 50 < 1e-6)


def test_library_scan_search_icons_and_refresh():
    comp_dir = os.path.join(TMP, "scan", "components")
    bg_dir = os.path.join(TMP, "scan", "backgrounds")
    make_asset(os.path.join(comp_dir, "nickel_foam.png"))
    make_asset(os.path.join(comp_dir, "PPY-coating.png"))
    Image.new("RGB", (80, 60), (10, 120, 10)).save(os.path.join(comp_dir, "NiMoO4 rod.jpg"))
    make_asset(os.path.join(comp_dir, "sub", "nested_item.png"))
    open(os.path.join(comp_dir, "notes.txt"), "w").write("not an image")
    open(os.path.join(comp_dir, "broken.png"), "wb").write(b"\x89PNG garbage")
    os.makedirs(bg_dir, exist_ok=True)
    Image.new("RGB", (120, 80), (200, 200, 220)).save(os.path.join(bg_dir, "base.png"))

    lib = LibraryDock(components_dir=comp_dir, backgrounds_dir=bg_dir)
    from PyQt6.QtWidgets import QListView
    assert lib.list.viewMode() == QListView.ViewMode.IconMode
    names = lib.visible_names()
    assert sorted(names, key=str.lower) == ["PPY coating", "NiMoO4 rod", "nested item", "nickel foam"] or \
        sorted(names) == sorted(["PPY coating", "NiMoO4 rod", "nested item", "nickel foam"]), names
    assert len(names) == 4                                  # txt + corrupt png ignored
    for i in range(lib.list.count()):
        it = lib.list.item(i)
        assert not it.icon().isNull() and os.path.isfile(it.data(Qt.ItemDataRole.UserRole))
    # search filters by name (case-insensitive, partial)
    lib.search.setText("FOAM")
    assert lib.visible_names() == ["nickel foam"], lib.visible_names()
    assert "1 of 4" in lib.status.text()
    lib.search.setText("zzz")
    assert lib.visible_names() == [] and "No match" in lib.status.text()
    lib.search.clear()
    assert len(lib.visible_names()) == 4
    # category switch
    lib.set_category("background")
    assert lib.visible_names() == ["base"]
    lib.set_category("component")
    # new file appears on refresh and via add_files (no overwrite)
    make_asset(os.path.join(comp_dir, "late.png"))
    lib.refresh()
    assert "late" in lib.visible_names()
    src = make_asset(os.path.join(TMP, "outside", "late.png"))
    copied = lib.add_files([src, os.path.join(TMP, "outside", "x.txt")])
    assert len(copied) == 1 and os.path.basename(copied[0]) == "late_2.png"
    assert "late 2" in lib.visible_names()
    # live watcher picks up new files without a manual refresh
    make_asset(os.path.join(comp_dir, "watched_new.png"))
    for _ in range(40):
        QTest.qWait(100)
        if "watched new" in lib.visible_names():
            break
    assert "watched new" in lib.visible_names(), lib.visible_names()
    # empty folder -> helpful message
    empty = LibraryDock(components_dir=os.path.join(TMP, "emptydir"), backgrounds_dir=bg_dir)
    assert empty.list.count() == 0 and "No images found" in empty.status.text()


def test_main_window_library_dock_placement_and_samples():
    w = make_window()
    assert w.dockWidgetArea(w.library) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert w.library.y() > w.layers.y()                      # below the Layers dock
    assert w.library.windowTitle() == "Component Library"
    names = w.library.visible_names()
    assert len(names) >= 5, names                            # shipped sample assets
    view_menu = [m for m in w.menuBar().findChildren(type(w.menuBar())) if False]
    texts = [a.text() for a in w.menuBar().actions()]
    assert "&View" in texts


def test_library_drag_and_drop_onto_canvas():
    w = make_window()
    cv = w.canvas_view
    lib = w.library
    lib.search.setText("foam")
    foam = first_visible(lib)
    assert foam.text() == "nickel foam"
    # the list produces a proper drag payload
    mime = lib.list.mimeData([foam])
    assert mime.hasFormat(al.ASSET_MIME)
    assert al.decode_assets(bytes(mime.data(al.ASSET_MIME)))[0][0] == "component"

    target = QPointF(433.0, 301.0)
    acc_enter, acc_drop = send_drop(w, mime, target)
    assert acc_enter and acc_drop
    comps = components(w)
    assert len(comps) == 1
    c = center_of(comps[0])
    assert abs(c.x() - target.x()) <= 1.0 and abs(c.y() - target.y()) <= 1.0, (c, target)   # exact drop spot
    assert comps[0].isSelected() and rows(w)[0] == "Component: nickel foam"

    # grid snapping applies to the drop position
    w.grid_spin.setValue(50)
    w.act_grid.setChecked(True)
    send_drop(w, mime, QPointF(433.0, 301.0))
    c = center_of(components(w)[-1])
    assert abs(c.x() - 450) <= 0.6 and abs(c.y() - 300) <= 0.6, c
    w.act_grid.setChecked(False)

    # multiple selected thumbnails -> multiple items
    lib.search.clear()
    for i in range(lib.list.count()):
        lib.list.item(i).setSelected(i < 2)
    assert len(lib.list.selectedItems()) == 2
    n = len(components(w))
    send_drop(w, lib.list.mimeData(lib.list.selectedItems()), QPointF(300, 250))
    assert len(components(w)) == n + 2

    # a background thumbnail replaces the canvas background
    lib.set_category("background")
    bg = first_visible(lib)
    send_drop(w, lib.list.mimeData([bg]), QPointF(100, 100))
    assert w.canvas_view.background_path == bg.data(Qt.ItemDataRole.UserRole)

    # image files dragged from the OS file manager work too
    img = make_asset(os.path.join(TMP, "os_drop", "from_desktop.png"))
    m2 = QMimeData(); m2.setUrls([QUrl.fromLocalFile(img)])
    n = len(components(w))
    send_drop(w, m2, QPointF(200, 200))
    assert len(components(w)) == n + 1
    # unrelated drops are ignored
    m3 = QMimeData(); m3.setText("hello")
    m4 = QMimeData(); m4.setUrls([QUrl.fromLocalFile(os.path.join(TMP, "bad.chem"))])
    send_drop(w, m3, QPointF(200, 200))           # plain text
    send_drop(w, m4, QPointF(200, 200))           # non-image file URL
    assert len(components(w)) == n + 1


def test_component_default_size_fits_canvas():
    w = make_window(bg=False)                                  # 1200 x 800 canvas
    cv = w.canvas_view
    tall = make_asset(os.path.join(TMP, "lib1", "tall.png"), size=(90, 420))
    huge = make_asset(os.path.join(TMP, "lib1", "huge.png"), size=(4000, 3000))
    tiny = make_asset(os.path.join(TMP, "lib1", "tiny.png"), size=(40, 30))
    for path in (tall, huge, tiny):
        it = cv.add_component(path)
        r = it.sceneBoundingRect()
        assert r.width() <= 0.25 * 1200 + 1 and r.height() <= 0.40 * 800 + 1, (path, r)
        assert it.scale() <= 4.0
    # huge image really was shrunk, tall one limited by height
    assert components(w)[1].scale() < 0.1


def test_library_double_click_and_insert_button():
    w = make_window()
    cv = w.canvas_view
    lib = w.library
    lib.search.setText("nanorod")
    item = first_visible(lib)
    lib.list.itemDoubleClicked.emit(item)                    # double-click
    app.processEvents()
    comps = components(w)
    assert len(comps) == 1 and "nanorod" in comps[0].layer_name()
    vc = cv.mapToScene(cv.viewport().rect().center())        # centre of the visible canvas
    c = center_of(comps[0])
    assert abs(c.x() - vc.x()) <= 1.0 and abs(c.y() - vc.y()) <= 1.0, (c, vc)
    # tool is reset to Select
    w.tool_actions["arrow"].trigger()
    lib.list.clearSelection(); item.setSelected(True)
    assert lib.btn_insert.isEnabled()
    lib.btn_insert.click()
    assert len(components(w)) == 2 and cv.tool == "select"
    # real double-click on the thumbnail works as well
    lib.show(); app.processEvents()
    rect = lib.list.visualItemRect(item)
    if rect.isValid() and rect.width() > 0:
        # (QTest needs a preceding click to register the pressed index, like a real user)
        QTest.mouseClick(lib.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        QTest.mouseDClick(lib.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
        app.processEvents()
        assert len(components(w)) == 3
    # backgrounds: double-click sets the background
    lib.search.clear()
    lib.set_category("background")
    first = first_visible(lib)
    lib.list.itemDoubleClicked.emit(first)
    assert cv.background_path == first.data(Qt.ItemDataRole.UserRole)


def test_component_save_load_relative_paths_and_missing_files():
    saved_assets = al.ASSETS_DIR
    from pathlib import Path
    fake_assets = Path(TMP) / "assets_x"
    al.ASSETS_DIR = fake_assets
    try:
        lib_img = make_asset(str(fake_assets / "components" / "lib_item.png"))
        proj = os.path.join(TMP, "projA")
        local_img = make_asset(os.path.join(proj, "img", "local_item.png"))
        w = make_window(bg=False)
        cv = w.canvas_view
        a = cv.add_component(local_img, at=QPointF(300, 200))
        a.setScale(0.8); a.setRotation(15); a.setOpacity(0.35); a.set_flip(True, False)
        b = cv.add_component(lib_img, at=QPointF(800, 500))
        b.set_flip(False, True)
        m = cv.add_molecule(MOLECULE_TYPES[1]); m.setPos(500, 100)
        cv.move_z([a], +1)                                   # a is now above b
        cv.set_locked([b], True)
        before_order = [i.layer_name() for i in cv.annotation_items()]
        before_dict = cv.to_dict()["components"]

        saved = w.save_project_to(os.path.join(proj, "demo"))
        raw = json.load(open(saved, encoding="utf-8"))
        comps = {os.path.basename(c["absolute_path"]): c for c in raw["components"]}
        assert comps["local_item.png"]["path"] == "img/local_item.png", comps       # relative to .chem
        assert comps["local_item.png"]["asset"] is None
        assert comps["lib_item.png"]["asset"] == "components/lib_item.png"
        assert comps["lib_item.png"]["path"].startswith("../assets_x/"), comps["lib_item.png"]
        assert raw["version"] == 2
        for c in raw["components"]:
            for k in ("x", "y", "scale", "opacity", "flip_h", "flip_v", "z", "locked"):
                assert k in c

        def check(win):
            got = {os.path.basename(c["path"]): c for c in win.canvas_view.to_dict()["components"]}
            for old in before_dict:
                new = got[os.path.basename(old["path"])]
                for k in ("x", "y", "scale", "rotation", "opacity", "flip_h", "flip_v", "z", "locked"):
                    if isinstance(old[k], float):
                        assert abs(new[k] - old[k]) < 1e-6, (k, new[k], old[k])
                    else:
                        assert new[k] == old[k], (k, new[k], old[k])
            assert [i.layer_name() for i in win.canvas_view.annotation_items()] == before_order

        w2 = make_window(bg=False)
        assert w2.open_project_file(saved) == []
        check(w2)
        assert cv.export_to_pil(600).tobytes() == w2.canvas_view.export_to_pil(600).tobytes()

        # whole project folder moved: relative path of the local image still works,
        # library asset falls back to its absolute path
        moved = os.path.join(TMP, "projB")
        shutil.copytree(proj, moved)
        shutil.rmtree(proj)
        w3 = make_window(bg=False)
        assert w3.open_project_file(os.path.join(moved, "demo.chem")) == []
        check(w3)
        assert any(os.path.dirname(os.path.dirname(c.source_path)) == os.path.abspath(moved)
                   for c in components(w3))

        # break path + absolute_path: library assets are found via the assets folder
        raw = json.load(open(os.path.join(moved, "demo.chem"), encoding="utf-8"))
        for c in raw["components"]:
            if c["asset"]:
                c["path"], c["absolute_path"] = "nowhere/x.png", "/definitely/missing/x.png"
        json.dump(raw, open(os.path.join(moved, "demo.chem"), "w", encoding="utf-8"))
        w4 = make_window(bg=False)
        assert w4.open_project_file(os.path.join(moved, "demo.chem")) == []
        check(w4)

        # delete a referenced image: warning + visible placeholder; link survives a re-save
        os.remove(os.path.join(moved, "img", "local_item.png"))
        w5 = make_window(bg=False)
        warn = w5.open_project_file(os.path.join(moved, "demo.chem"))
        assert any("Component image not found" in x for x in warn), warn
        missing = [c for c in components(w5) if c.missing]
        assert len(missing) == 1 and missing[0].layer_name().endswith("(missing)")
        assert abs(missing[0].opacity() - 0.35) < 1e-9 and missing[0].flip_h
        resaved = w5.save_project_to(os.path.join(moved, "resaved"))
        again = json.load(open(resaved, encoding="utf-8"))
        assert any(c["path"] == "img/local_item.png" for c in again["components"]), again["components"]

        # corrupt (but existing) image -> readable warning, project still opens
        open(os.path.join(moved, "img", "local_item.png"), "wb").write(b"not an image")
        w6 = make_window(bg=False)
        warn = w6.open_project_file(os.path.join(moved, "demo.chem"))
        assert any("Could not read component image" in x for x in warn), warn
        assert len(components(w6)) == 2
    finally:
        al.ASSETS_DIR = saved_assets


def test_old_v1_projects_still_load():
    path = os.path.join(TMP, "v1.chem")
    json.dump({"format": "chem-project", "version": 1, "canvas": {"width": 900, "height": 600},
               "molecules": [{"kind": MOLECULE_TYPES[0], "x": 10, "y": 20}],
               "texts": [], "arrows": []}, open(path, "w"))
    w = make_window(bg=False)
    assert w.open_project_file(path) == []
    assert len(w.canvas_view.annotation_items()) == 1 and components(w) == []
    # invalid component entries are skipped with a warning
    json.dump({"format": "chem-project", "version": 2,
               "components": [{"x": 1}, "junk", {"path": "a.png", "opacity": 7}]}, open(path, "w"))
    data, warnings = pm.load_project(path)
    assert len(data["components"]) == 1 and data["components"][0]["opacity"] == 1.0
    assert len(warnings) >= 3, warnings


def test_asset_library_helpers():
    from pathlib import Path
    assert al.display_name("/x/y/nickel_foam-v2.png") == "nickel foam v2"
    assert al.is_image_file("A.PNG") and al.is_image_file("b.jpeg") and not al.is_image_file("c.gif")
    d = os.path.join(TMP, "uniq"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "a.png"), "w").close()
    assert os.path.basename(al.unique_destination(d, "a.png")) == "a_2.png"
    saved = al.ASSETS_DIR
    al.ASSETS_DIR = Path(TMP) / "assets_y"
    try:
        assert al.asset_relative_path(Path(TMP) / "assets_y" / "components" / "z.png") == "components/z.png"
        assert al.asset_relative_path("/etc/passwd") is None
        assert al.resolve_asset_path("../../etc/passwd") is None        # no path traversal
        assert al.resolve_asset_path("components/z.png").endswith(os.path.join("components", "z.png"))
    finally:
        al.ASSETS_DIR = saved
    assert al.decode_assets(b"garbage") == [] and al.decode_assets(b'[{"kind":"component","path":"/nope.png"}]') == []


if __name__ == "__main__":
    failed = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
