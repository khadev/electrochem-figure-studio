"""Scientific Schematic Editor - application entry point."""
import os
import sys

# Make sure matplotlib's Qt backend binds to PyQt6.
os.environ.setdefault("QT_API", "pyqt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Scientific Schematic Editor")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
