
# ⚗️ Electrochem Figure Studio

> A professional, native desktop application for chemists and materials scientists to compose publication-ready electrochemical figures.

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

**Electrochem Figure Studio** combines an interactive 3D-render schematic editor with a mathematical Cyclic Voltammetry (CV) graph generator. It eliminates the need for clunky image stitching by allowing you to compose, annotate, and export high-resolution (300 dpi) vertically stacked figures—all within a single, unified workspace.

---

## ✨ Features

*   🎨 **Interactive Canvas:** Load a 3D material render (PNG/JPG) as the background and drag-and-drop vector-based molecules (Methanol, CO₂, H₂), text labels, and reaction arrows.
*   📊 **Dynamic CV Generator:** Natively embedded Matplotlib widget generates `Reversible`, `Irreversible`, and `Catalytic Wave` curves with adjustable peak heights and positions.
*   🗂️ **Layer Management:** A fully featured Layers dock to reorder (z-index), select, and lock items to prevent accidental movement.
*   🎛️ **Properties Panel:** Context-sensitive editing. Change fonts, colors, molecule scales, and arrow thicknesses dynamically.
*   📐 **Grid & Snapping:** Toggle an alignment grid (Ctrl+G) to ensure perfect alignment of your molecules and text.
*   💾 **Project Save/Load:** Save your entire workspace (background path, molecules, text, arrows, and graph settings) to a lightweight `.chem` JSON file.
*   🖨️ **One-Click Export:** Automatically stitch the canvas and the CV graph into a single, high-resolution PNG (2400px wide, 300 dpi), ready for manuscript submission.

---

## 🚀 Installation & Setup

It is highly recommended to use a virtual environment to manage dependencies.

### 1. Clone the repository
```bash
git clone https://github.com/khadev/electrochem-figure-studio.git
cd electrochem-figure-studio
```

2. Create a virtual environment

Windows:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Launch the application

```bash
python main.py
```

---

📖 How to Use

1. Load Background: Go to File → Load Background Image (Ctrl+B) to set your 3D material render.
2. Add Elements: Use the top toolbar to add molecules, text, or draw arrows. Use the right-hand Properties panel to edit their appearance.
3. Manage Layers: Use the left-hand Layers panel to ensure text is always readable and arrows sit on top of molecules.
4. Tune the Graph: Use the Controls dock to adjust the CV curve type, peak height, and peak position. Click "Update Graph".
5. Export: Go to File → Export → Export Combined Figure (Ctrl+E) to save your final, vertically stacked publication image.

---

🏗️ Architecture

The project is built with a strict separation of concerns (GUI vs. Logic) for maintainability and testing.

```text
electrochem-figure-studio/
│
├── main.py                 # Application entry point
├── requirements.txt        # Dependencies
│
├── core/                   # Pure Python logic (No PyQt6 dependencies)
│   ├── cv_generator.py     # NumPy/Matplotlib CV mathematics
│   ├── image_exporter.py   # PIL-based vertical image stitching
│   └── project_manager.py  # JSON project save/load validation
│
├── gui/                    # PyQt6 Interface
│   ├── main_window.py      # Main window, layouts, and menus
│   ├── canvas_view.py      # QGraphicsScene (zoom, pan, grid, snapping)
│   ├── graph_view.py       # Embedded Matplotlib canvas
│   ├── items.py            # Custom QGraphicsItems (Molecules, Text, Arrows)
│   ├── layers_dock.py      # Layer manager UI
│   ├── properties_dock.py  # Context menu UI
│   └── controls_dock.py    # CV graph parameter sliders
│
└── tests/                  # Automated testing
    └── test_features.py    # Headless UI and logic tests (python tests/test_features.py)
```

---

🧪 Testing

To ensure all mathematical models and UI interactions function correctly without opening a display, run the headless test suite:

```bash
python tests/test_features.py
```

---

🤝 Contributing

Contributions, issues, and feature requests are welcome! 
If you want to add a new molecule (e.g., Ethanol) or a new CV curve type, feel free to fork the repository, modify gui/items.py or core/cv_generator.py, and submit a pull request.

📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

