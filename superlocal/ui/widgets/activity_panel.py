"""
SuperLocal Live Activity Timeline Panel
Collapsible right panel showing:
- Real-time step progress (Step N/8, tool name, execution time)
- Tool outputs and status icons
- Prominent RED STOP button (also Ctrl+Alt+Q) and Pause button
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QPlainTextEdit,
)
from superlocal.ui.theme import Colors


class StepTimelineItem(QFrame):
    """Card representing a single step execution in the timeline."""

    def __init__(self, step: int, tool_name: str, elapsed: float, parent=None):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setStyleSheet("""
            QFrame[card="true"] {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px;
                margin-bottom: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self.icon_label = QLabel("⏳", self)
        self.title_label = QLabel(f"Step {step}: {tool_name}", self)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.time_label = QLabel(f"{elapsed:.1f}s", self)
        self.time_label.setStyleSheet("color: #888888; font-size: 11px;")

        header.addWidget(self.icon_label)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.time_label)
        layout.addLayout(header)

        self.output_label = QLabel("Running...", self)
        self.output_label.setStyleSheet("color: #AAAAAA; font-size: 11px; font-family: Consolas, monospace;")
        self.output_label.setWordWrap(True)
        layout.addWidget(self.output_label)

    def mark_finished(self, success: bool, output: str, duration: float):
        self.icon_label.setText("✔" if success else "✖")
        icon_color = Colors.SUCCESS if success else Colors.DANGER
        self.icon_label.setStyleSheet(f"color: {icon_color}; font-size: 12px;")
        self.time_label.setText(f"{duration:.2f}s")
        # Truncate output preview to 200 chars
        clean_out = (output or "").strip()
        if len(clean_out) > 200:
            clean_out = clean_out[:200] + "..."
        self.output_label.setText(clean_out or "(no output)")


class ActivityPanel(QWidget):
    """Right-side live task timeline panel with controls."""

    stop_requested = Signal()
    pause_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header title
        title_box = QHBoxLayout()
        header_title = QLabel("Live Activity", self)
        header_title.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.setFixedHeight(24)
        self.clear_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.clear_btn.clicked.connect(self.clear_timeline)

        title_box.addWidget(header_title)
        title_box.addStretch()
        title_box.addWidget(self.clear_btn)
        main_layout.addLayout(title_box)

        # Control Buttons: STOP & PAUSE
        btn_layout = QHBoxLayout()
        self.stop_btn = QPushButton("⛔ STOP (Ctrl+Alt+Q)", self)
        self.stop_btn.setProperty("danger", "true")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setFixedHeight(34)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

        self.pause_btn = QPushButton("⏸ Pause", self)
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.setFixedHeight(34)
        self.pause_btn.clicked.connect(self.pause_requested.emit)

        btn_layout.addWidget(self.stop_btn, stretch=2)
        btn_layout.addWidget(self.pause_btn, stretch=1)
        main_layout.addLayout(btn_layout)

        # Scrollable Timeline Area
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(6)
        self.timeline_layout.addStretch()
        self.scroll.setWidget(self.timeline_container)

        main_layout.addWidget(self.scroll)

        self._active_items = {}

    def on_step_started(self, step: int, tool_name: str, elapsed: float):
        item = StepTimelineItem(step, tool_name, elapsed, self.timeline_container)
        # Insert before the stretch at the end
        self.timeline_layout.insertWidget(self.timeline_layout.count() - 1, item)
        self._active_items[step] = item

    def on_step_finished(self, step: int, tool_name: str, success: bool, output: str, duration: float):
        if step in self._active_items:
            self._active_items[step].mark_finished(success, output, duration)

    def set_paused_state(self, is_paused: bool):
        self.pause_btn.setText("▶ Resume" if is_paused else "⏸ Pause")

    def clear_timeline(self):
        for item in self._active_items.values():
            item.setParent(None)
            item.deleteLater()
        self._active_items.clear()
