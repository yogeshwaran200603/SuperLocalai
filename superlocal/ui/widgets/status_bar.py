"""
SuperLocal Bottom Status Bar
Displays:
- Engine state (Idle / Working / Waiting for approval)
- Microphone state
- Active workspace folder
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from superlocal.ui.theme import Colors


class StatusBar(QWidget):
    """Bottom status bar with real-time indicators."""

    def __init__(self, workspace_path: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.setSpacing(16)

        # Engine State
        self.engine_dot = QLabel("●", self)
        self.engine_dot.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
        self.engine_label = QLabel("Idle", self)
        self.engine_label.setStyleSheet("font-size: 11px; color: #999999;")

        layout.addWidget(self.engine_dot)
        layout.addWidget(self.engine_label)

        sep1 = QFrame(self)
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #444444; max-height: 14px;")
        layout.addWidget(sep1)

        # Mic State
        self.mic_icon = QLabel("🎙️", self)
        self.mic_icon.setStyleSheet("font-size: 12px;")
        self.mic_label = QLabel("Mic: Off", self)
        self.mic_label.setStyleSheet("font-size: 11px; color: #999999;")

        layout.addWidget(self.mic_icon)
        layout.addWidget(self.mic_label)

        layout.addStretch()

        # Workspace path
        self.folder_icon = QLabel("📁", self)
        self.folder_icon.setStyleSheet("font-size: 12px;")
        self.workspace_label = QLabel(workspace_path or "Workspace: .", self)
        self.workspace_label.setStyleSheet("font-size: 11px; color: #888888;")

        layout.addWidget(self.folder_icon)
        layout.addWidget(self.workspace_label)

    def set_engine_state(self, state_text: str):
        self.engine_label.setText(state_text)
        state_lower = state_text.lower()
        if "work" in state_lower or "think" in state_lower:
            self.engine_dot.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px;")
        elif "wait" in state_lower or "approval" in state_lower:
            self.engine_dot.setStyleSheet(f"color: {Colors.WARNING}; font-size: 11px;")
        elif "error" in state_lower or "stop" in state_lower:
            self.engine_dot.setStyleSheet(f"color: {Colors.DANGER}; font-size: 11px;")
        else:
            self.engine_dot.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")

    def set_mic_state(self, state_val):
        if isinstance(state_val, bool):
            txt = "Listening" if state_val else "Off"
        else:
            txt = str(state_val)
        self.mic_label.setText(f"Mic: {txt}")

    set_mic_status = set_mic_state

    def set_workspace(self, path_str: str):
        self.workspace_label.setText(path_str)
