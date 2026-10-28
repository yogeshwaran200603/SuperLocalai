"""
SuperLocal Quick Command Bar (Spotlight Style)
Centered floating popup input bar triggered via Ctrl+Alt+Space.
Press Enter to submit to engine; Escape to dismiss.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QKeyEvent
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QApplication,
    QGraphicsDropShadowEffect,
)
from superlocal.ui.theme import Colors


class QuickCommandBar(QWidget):
    """Spotlight-like floating command input."""

    submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(620, 70)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Container card
        self.card = QWidget(self)
        self.card.setStyleSheet(f"""
            background-color: {Colors.SURFACE};
            border: 1px solid {Colors.ACCENT};
            border-radius: 12px;
        """)
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(10)

        icon_label = QLabel("✨", self.card)
        icon_label.setStyleSheet("font-size: 18px;")
        card_layout.addWidget(icon_label)

        self.input_edit = QLineEdit(self.card)
        self.input_edit.setPlaceholderText("Ask SuperLocal anything... (e.g. 'open notepad', '/auto build a portfolio')")
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                font-size: 15px;
                color: #FFFFFF;
            }
        """)
        self.input_edit.returnPressed.connect(self._on_submit)
        card_layout.addWidget(self.input_edit, stretch=1)

        run_btn = QPushButton("Run ↵", self.card)
        run_btn.setProperty("accent", "true")
        run_btn.setFixedHeight(32)
        run_btn.clicked.connect(self._on_submit)
        card_layout.addWidget(run_btn)

        main_layout.addWidget(self.card)

    def show_centered(self):
        """Center the quick bar on screen and focus input."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = (geom.width() - self.width()) // 2
            y = int(geom.height() * 0.22)
            self.move(x, y)
        self.input_edit.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_edit.setFocus()

    def _on_submit(self):
        text = self.input_edit.text().strip()
        if text:
            self.submitted.emit(text)
        self.hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
