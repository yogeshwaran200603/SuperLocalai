"""
SuperLocal Control Overlay Pill
Always-on-top transparent floating pill at screen top:
"SuperLocal is in control - Ctrl+Alt+Q to stop"
With current step indicator, Pause and Stop buttons.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
    QFrame,
)
from superlocal.ui.theme import Colors


class ControlOverlayPill(QWidget):
    """Floating transparent overlay pill displayed during active automation."""

    stop_requested = Signal()
    pause_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(50)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Pill container
        self.pill = QFrame(self)
        self.pill.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(26, 31, 46, 230);
                border: 1px solid rgba(0, 120, 212, 180);
                border-radius: 20px;
                padding: 4px 12px;
            }}
        """)
        pill_layout = QHBoxLayout(self.pill)
        pill_layout.setContentsMargins(10, 4, 10, 4)
        pill_layout.setSpacing(10)

        # Pulsing dot
        self.dot = QLabel("●", self.pill)
        self.dot.setStyleSheet("color: #107C41; font-size: 14px;")
        pill_layout.addWidget(self.dot)

        # Status text
        self.status_label = QLabel("SuperLocal is in control • <b>Ctrl+Alt+Q</b> to stop", self.pill)
        self.status_label.setStyleSheet("color: #FFFFFF; font-size: 12px;")
        pill_layout.addWidget(self.status_label)

        # Current step text
        self.step_label = QLabel("", self.pill)
        self.step_label.setStyleSheet("color: #0078D4; font-size: 11px; font-weight: bold;")
        self.step_label.hide()
        pill_layout.addWidget(self.step_label)

        # Pause button
        self.pause_btn = QPushButton("⏸ Pause", self.pill)
        self.pause_btn.setFixedHeight(26)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 13px;
                color: #FFFFFF;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.pause_btn.clicked.connect(self.pause_requested.emit)
        pill_layout.addWidget(self.pause_btn)

        # Stop button
        self.stop_btn = QPushButton("⏹ Stop", self.pill)
        self.stop_btn.setFixedHeight(26)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.DANGER};
                border: none;
                border-radius: 13px;
                color: #FFFFFF;
                font-weight: bold;
                padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: #B02020;
            }}
        """)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        pill_layout.addWidget(self.stop_btn)

        main_layout.addWidget(self.pill)
        self.adjustSize()

    def update_step(self, step_name: str):
        if step_name:
            self.step_label.setText(f"[{step_name}]")
            self.step_label.show()
        else:
            self.step_label.hide()
        self.adjustSize()
        self._position_top_center()

    def set_paused_state(self, is_paused: bool):
        if is_paused:
            self.dot.setStyleSheet("color: #F59E0B; font-size: 14px;")
            self.status_label.setText("SuperLocal Paused")
            self.pause_btn.setText("▶ Resume")
        else:
            self.dot.setStyleSheet("color: #107C41; font-size: 14px;")
            self.status_label.setText("SuperLocal is in control • <b>Ctrl+Alt+Q</b> to stop")
            self.pause_btn.setText("⏸ Pause")

    def show_pill(self):
        self._position_top_center()
        self.show()
        self.raise_()

    def _position_top_center(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.width()) // 2
            y = 20
            self.move(x, y)
