"""
SuperLocal Desktop GUI Entry Point
Executable via:
  python -m superlocal.gui
"""

import sys
import os
from pathlib import Path

# Ensure root workspace is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure STA threading mode for pywinauto on Windows
if sys.platform == "win32" and not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 2

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from superlocal.ui.main_window import SuperLocalMainWindow
from core.engine import get_engine


def main():
    # High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setApplicationName("SuperLocal")
    app.setApplicationDisplayName("SuperLocal")

    engine = get_engine()
    window = SuperLocalMainWindow(engine=engine)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
