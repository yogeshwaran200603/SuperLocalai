"""
Render Stage 3 Settings Page headless screenshot.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from superlocal.ui.main_window import SuperLocalMainWindow
from core.engine import SuperLocalEngine
from pathlib import Path

def main():
    app = QApplication.instance() or QApplication([])
    engine = SuperLocalEngine()
    win = SuperLocalMainWindow(engine=engine)
    win.resize(1180, 760)
    win.show()

    # Switch to Settings Page (index 7)
    win.sidebar.select_page(7)

    app.processEvents()

    out_path = Path("logs/gui_render_stage3.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    pix.save(str(out_path), "PNG")
    print(f"Captured screenshot to {out_path.resolve()}")

if __name__ == "__main__":
    main()
