"""
Render Stage 5 Workbench pages headless screenshots.
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from superlocal.ui.main_window import SuperLocalMainWindow
from core.engine import SuperLocalEngine

def main():
    app = QApplication.instance() or QApplication([])
    engine = SuperLocalEngine()
    win = SuperLocalMainWindow(engine=engine)
    win.resize(1180, 760)
    win.show()

    # Switch to Games Page (index 3)
    win.sidebar.select_page(3)
    app.processEvents()

    out_path = Path("logs/gui_render_stage5_games.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix = win.grab()
    pix.save(str(out_path), "PNG")
    print(f"Captured screenshot to {out_path.resolve()}")

    # Switch to Optimizer Page (index 4)
    win.sidebar.select_page(4)
    app.processEvents()
    out_path_opt = Path("logs/gui_render_stage5_optimizer.png")
    win.grab().save(str(out_path_opt), "PNG")
    print(f"Captured screenshot to {out_path_opt.resolve()}")

if __name__ == "__main__":
    main()
