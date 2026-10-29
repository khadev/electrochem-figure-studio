# Scientific Schematic Editor (PyQt6) — Enterprise edition

## Run
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python main.py

## Layout
    main.py
    core/   (no Qt)  cv_generator.py · image_exporter.py · project_manager.py
    gui/             main_window.py · canvas_view.py · graph_view.py · items.py
                     controls_dock.py · layers_dock.py · properties_dock.py · icons.py
    tests/           test_features.py   (headless: python tests/test_features.py)

## Features
- **Toolbar**: Select · Pan · Arrow · Molecule (drop-down) · Text · Delete · Grid · Snap (+ grid size) · Fit.
- **Layers dock (left)**: all items, top-most first. Click to select on canvas (and vice-versa,
  multi-select supported); Up/Down change z-order; Lock/Unlock prevents accidental moves.
- **Properties dock (right, below Controls)**: Text → text, font family, size, bold, colour;
  Molecule → scale and rotation sliders; Arrow → colour (QColorDialog) and thickness.
- **Grid & snapping**: Ctrl+G toggles the overlay; while the grid is on (and Snap is on) dragged items
  and new arrows snap to grid intersections. The grid is never exported.
- **Projects**: File → Save Project (Ctrl+S) / Save As / Load Project (Ctrl+O) to `.chem` JSON files
  (background path stored relative to the project file, with absolute fallback).
- **Export**: File → Export → Export Combined Figure (PNG), 2400 px wide, 300 dpi.

## Mouse / keys
Ctrl+Wheel zoom · middle-drag or Pan tool to pan · double-click text to edit ·
Del removes selection · Esc returns to Select · Ctrl+0 fit to window.
