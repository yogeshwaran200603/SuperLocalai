"""
SuperLocal System Tray Icon
Provides background status, restore window, toggle voice, stop everything, and quit.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter
from PySide6.QtWidgets import (
    QSystemTrayIcon,
    QMenu,
    QApplication,
)
from superlocal.ui.theme import Colors


def create_default_tray_icon() -> QIcon:
    """Generate or load the SuperLocal app icon."""
    from pathlib import Path
    for p in [Path("assets/icon.ico"), Path("assets/icon.png")]:
        if p.exists():
            return QIcon(str(p))
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(0, 120, 212))
    painter.setPen(QColor(255, 255, 255))
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor(255, 255, 255))
    painter.drawText(pix.rect(), 0x0084, "SL")  # AlignCenter
    painter.end()
    return QIcon(pix)


class SuperLocalTrayIcon(QSystemTrayIcon):
    """System tray integration for SuperLocal."""

    restore_requested = Signal()
    stop_requested = Signal()
    voice_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, parent=None, icon: QIcon = None):
        super().__init__(parent)
        self.setIcon(icon or create_default_tray_icon())
        self.setToolTip("SuperLocal - Local AI Assistant")

        # Create tray context menu
        self.menu = QMenu()

        self.restore_action = self.menu.addAction("Show SuperLocal")
        self.restore_action.triggered.connect(self.restore_requested.emit)

        self.menu.addSeparator()

        self.voice_action = self.menu.addAction("Voice Listening")
        self.voice_action.setCheckable(True)
        self.voice_action.setChecked(True)
        self.voice_action.toggled.connect(self.voice_toggled.emit)

        self.stop_action = self.menu.addAction("Stop Everything (Ctrl+Alt+Q)")
        self.stop_action.triggered.connect(self.stop_requested.emit)

        self.menu.addSeparator()

        self.quit_action = self.menu.addAction("Quit SuperLocal")
        self.quit_action.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_requested.emit()
