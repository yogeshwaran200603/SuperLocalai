"""
SuperLocal Top Navigation Bar
Displays:
- Active provider and model with live status indicator dot
- Daily request count and progress quota bar
- Provider switcher dropdown
- Collapsible Activity Panel toggle button
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QProgressBar,
    QPushButton,
    QFrame,
)
from superlocal.ui.theme import Colors
from config import PROVIDER_ORDER


class TopBar(QWidget):
    """Header bar with provider controls, quota status, and activity toggle."""

    provider_selected = Signal(str)
    activity_toggle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)

        # 1. Provider & Status Dot
        self.status_dot = QLabel("●", self)
        self.status_dot.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 14px;")

        self.provider_combo = QComboBox(self)
        for p in PROVIDER_ORDER:
            self.provider_combo.addItem(p)
        self.provider_combo.currentTextChanged.connect(self.provider_selected.emit)

        self.model_label = QLabel("gemini-3.8-flash", self)
        self.model_label.setStyleSheet("color: #888888; font-size: 12px;")

        layout.addWidget(self.status_dot)
        layout.addWidget(self.provider_combo)
        layout.addWidget(self.model_label)

        layout.addStretch()

        # 2. Quota Progress Bar
        self.quota_label = QLabel("Requests today: 0 / 1000", self)
        self.quota_label.setStyleSheet("font-size: 12px; color: #888888;")

        self.quota_bar = QProgressBar(self)
        self.quota_bar.setFixedWidth(120)
        self.quota_bar.setFixedHeight(6)
        self.quota_bar.setTextVisible(False)
        self.quota_bar.setRange(0, 1000)
        self.quota_bar.setValue(0)

        layout.addWidget(self.quota_label)
        layout.addWidget(self.quota_bar)

        # Separator
        sep = QFrame(self)
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #444444; max-height: 20px;")
        layout.addWidget(sep)

        # 3. Activity Panel Toggle
        self.toggle_activity_btn = QPushButton("Activity ❯", self)
        self.toggle_activity_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_activity_btn.setToolTip("Toggle Live Task Activity Timeline")
        self.toggle_activity_btn.clicked.connect(self.activity_toggle_requested.emit)
        layout.addWidget(self.toggle_activity_btn)

    def update_provider_info(self, provider_name: str, model_name: str, is_online: bool = True):
        idx = self.provider_combo.findText(provider_name)
        if idx >= 0:
            self.provider_combo.blockSignals(True)
            self.provider_combo.setCurrentIndex(idx)
            self.provider_combo.blockSignals(False)

        self.model_label.setText(model_name)
        dot_color = Colors.SUCCESS if is_online else Colors.DANGER
        self.status_dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")

    def update_quota(self, used: int, limit: int = 1000):
        self.quota_label.setText(f"Requests today: {used} / {limit}")
        self.quota_bar.setRange(0, max(1, limit))
        self.quota_bar.setValue(min(used, limit))

        # Color warning if near quota
        if used >= int(limit * 0.8):
            self.quota_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {Colors.WARNING}; }}")
        else:
            self.quota_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {Colors.ACCENT}; }}")

    def set_activity_button_state(self, is_open: bool):
        self.toggle_activity_btn.setText("Activity ❯" if is_open else "Activity ❮")
