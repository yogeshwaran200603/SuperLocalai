"""
SuperLocal Navigation Sidebar
Clean left sidebar with icons and labels for:
Chat, Tasks, Voice, Games, Optimizer, Skills/Tools, History, Settings.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
)
from superlocal.ui.theme import Colors


class SidebarItem(QPushButton):
    """Custom styled sidebar button with icon and label."""

    def __init__(self, icon_text: str, label_text: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        self.icon_label = QLabel(icon_text, self)
        self.icon_label.setStyleSheet("font-size: 16px; background: transparent;")
        self.icon_label.setFixedWidth(24)

        self.text_label = QLabel(label_text, self)
        self.text_label.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self._update_style(False)

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._update_style(checked)

    def _update_style(self, checked: bool):
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT};
                    border: none;
                    border-radius: 6px;
                }}
                QLabel {{
                    color: #FFFFFF;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.08);
                }}
                QLabel {{
                    color: inherit;
                }}
            """)


class Sidebar(QWidget):
    """Navigation sidebar hosting 8 main application destinations."""

    page_changed = Signal(int)

    NAV_ITEMS = [
        ("💬", "Chat"),
        ("⚡", "Tasks"),
        ("🎙️", "Voice"),
        ("🎮", "Games"),
        ("🚀", "Optimizer"),
        ("🛠️", "Skills / Tools"),
        ("📜", "History"),
        ("⚙️", "Settings"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        # Header branding
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 4, 8, 16)
        logo_icon = QLabel("✦", self)
        logo_icon.setStyleSheet(f"font-size: 20px; color: {Colors.ACCENT}; font-weight: bold;")
        brand_name = QLabel("SuperLocal", self)
        brand_name.setStyleSheet("font-size: 16px; font-weight: 700; letter-spacing: 0.5px;")

        header_layout.addWidget(logo_icon)
        header_layout.addWidget(brand_name)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Navigation buttons
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons = []

        for idx, (icon, text) in enumerate(self.NAV_ITEMS):
            btn = SidebarItem(icon, text, self)
            self.button_group.addButton(btn, idx)
            layout.addWidget(btn)
            self.buttons.append(btn)

        layout.addStretch()

        self.button_group.idClicked.connect(self._on_item_clicked)

        # Default select Chat
        if self.buttons:
            self.buttons[0].setChecked(True)

    def _on_item_clicked(self, page_index: int):
        for idx, btn in enumerate(self.buttons):
            btn._update_style(idx == page_index)
        self.page_changed.emit(page_index)

    def select_page(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)
            self._on_item_clicked(index)
