"""
SuperLocal Main Window
Combines:
- Left navigation sidebar
- Header Top Bar (provider, model, quota progress, activity toggle)
- Central Stacked Pages (Chat, Tasks, Voice, Games, Optimizer, Skills, History, Settings)
- Right Collapsible Live Activity Timeline Panel
- Bottom Status Bar
- Thread-safe Qt Signal Bridge connecting to Core Engine
- Safety Approval Dialog trigger
- Engine Crash Recovery & Restart Banner
"""

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QSplitter,
    QLabel,
    QPushButton,
    QFrame,
    QMessageBox,
)
from superlocal.ui.theme import Colors, get_stylesheet
from superlocal.ui.widgets.sidebar import Sidebar
from superlocal.ui.widgets.top_bar import TopBar
from superlocal.ui.widgets.status_bar import StatusBar
from superlocal.ui.widgets.activity_panel import ActivityPanel
from superlocal.ui.widgets.approval_dialog import ApprovalDialog
from superlocal.ui.pages.chat_page import ChatPage
from core.engine import get_engine, SuperLocalEngine, EngineState
from core.events import EventType, Event


class QtEventBridge(QObject):
    """Bridges background Engine events to the main Qt GUI thread via Qt signals."""

    message_received = Signal(dict)
    step_started = Signal(dict)
    step_finished = Signal(dict)
    tool_output = Signal(dict)
    approval_requested = Signal(dict)
    status_updated = Signal(dict)
    provider_changed = Signal(dict)
    quota_updated = Signal(dict)
    voice_state_updated = Signal(dict)
    error_occurred = Signal(dict)

    def dispatch(self, event: Event):
        name = event.name
        data = event.data
        if name == EventType.MESSAGE:
            self.message_received.emit(data)
        elif name == EventType.STEP_STARTED:
            self.step_started.emit(data)
        elif name == EventType.STEP_FINISHED:
            self.step_finished.emit(data)
        elif name == EventType.TOOL_OUTPUT:
            self.tool_output.emit(data)
        elif name == EventType.APPROVAL_REQUESTED:
            self.approval_requested.emit(data)
        elif name == EventType.STATUS:
            self.status_updated.emit(data)
        elif name == EventType.PROVIDER_CHANGED:
            self.provider_changed.emit(data)
        elif name == EventType.QUOTA_UPDATED:
            self.quota_updated.emit(data)
        elif name == EventType.VOICE_STATE:
            self.voice_state_updated.emit(data)
        elif name == EventType.ERROR:
            self.error_occurred.emit(data)


class SuperLocalMainWindow(QMainWindow):
    """Main desktop application window."""

    def __init__(self, engine: SuperLocalEngine = None, parent=None):
        super().__init__(parent)
        self.engine = engine or get_engine()
        self.bridge = QtEventBridge()

        self.setWindowTitle("SuperLocal")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(get_stylesheet(dark=True))

        # Root central container
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Crash / Error Recovery Banner (Hidden by default)
        self.error_banner = QFrame(self)
        self.error_banner.setStyleSheet(f"background-color: {Colors.DANGER}; padding: 6px 16px;")
        eb_layout = QHBoxLayout(self.error_banner)
        eb_layout.setContentsMargins(8, 4, 8, 4)
        self.error_msg_label = QLabel("An error occurred in the engine.", self.error_banner)
        self.error_msg_label.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        self.restart_engine_btn = QPushButton("Restart engine", self.error_banner)
        self.restart_engine_btn.setStyleSheet("background: #FFFFFF; color: #D13438; font-weight: bold; padding: 4px 10px;")
        self.restart_engine_btn.clicked.connect(self._on_restart_engine_clicked)
        eb_layout.addWidget(self.error_msg_label)
        eb_layout.addStretch()
        eb_layout.addWidget(self.restart_engine_btn)
        self.error_banner.hide()
        root_layout.addWidget(self.error_banner)

        # 2. Main Horizontal Body (Sidebar + Content Workspace + Activity Panel)
        body_widget = QWidget(self)
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self)
        self.sidebar.page_changed.connect(self._on_page_changed)
        body_layout.addWidget(self.sidebar)

        # Center Work Area (TopBar + Page Stack)
        center_area = QWidget(self)
        center_layout = QVBoxLayout(center_area)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Top Bar
        self.top_bar = TopBar(self)
        self.top_bar.provider_selected.connect(self.engine.set_provider)
        self.top_bar.activity_toggle_requested.connect(self.toggle_activity_panel)
        center_layout.addWidget(self.top_bar)

        # Stacked Pages
        self.page_stack = QStackedWidget(self)
        self.chat_page = ChatPage(self)
        self.chat_page.submit_prompt.connect(self.engine.submit)
        self.chat_page.voice_toggle_requested.connect(lambda: self.sidebar.select_page(2))

        self.page_stack.addWidget(self.chat_page)  # Index 0: Chat

        # Placeholder widgets for pages built in subsequent stages
        for i in range(1, 8):
            placeholder = QWidget(self)
            pl_layout = QVBoxLayout(placeholder)
            pl_label = QLabel(f"Page: {Sidebar.NAV_ITEMS[i][1]} (Loading in upcoming stage...)", placeholder)
            pl_label.setAlignment(Qt.AlignCenter)
            pl_layout.addWidget(pl_label)
            self.page_stack.addWidget(placeholder)

        center_layout.addWidget(self.page_stack, stretch=1)
        body_layout.addWidget(center_area, stretch=1)

        # Right Live Activity Panel (collapsible)
        self.activity_panel = ActivityPanel(self)
        self.activity_panel.stop_requested.connect(self.engine.stop)
        self.activity_panel.pause_requested.connect(self._on_toggle_pause)
        body_layout.addWidget(self.activity_panel)

        root_layout.addWidget(body_widget, stretch=1)

        # 3. Bottom Status Bar
        status_info = self.engine.get_status()
        self.status_bar = StatusBar(workspace_path=status_info.get("workspace", ""), parent=self)
        root_layout.addWidget(self.status_bar)

        # Initialize top bar status
        self.top_bar.update_provider_info(status_info.get("provider", "gemini"), status_info.get("model", "default"))
        self.top_bar.update_quota(status_info.get("requests_today", 0), status_info.get("quota_per_day", 1000))

        # Connect Qt event bridge to engine
        self._wire_engine_events()

    def _wire_engine_events(self):
        # Forward all engine events to Qt bridge
        self.engine.events.subscribe("*", self.bridge.dispatch)

        # Connect bridge signals to UI slots
        self.bridge.message_received.connect(self._on_message)
        self.bridge.step_started.connect(self._on_step_started)
        self.bridge.step_finished.connect(self._on_step_finished)
        self.bridge.approval_requested.connect(self._on_approval_requested)
        self.bridge.status_updated.connect(self._on_status)
        self.bridge.provider_changed.connect(self._on_provider_changed)
        self.bridge.quota_updated.connect(self._on_quota_updated)
        self.bridge.error_occurred.connect(self._on_error)

    def _on_page_changed(self, index: int):
        self.page_stack.setCurrentIndex(index)

    def toggle_activity_panel(self):
        is_visible = self.activity_panel.isVisible()
        self.activity_panel.setVisible(not is_visible)
        self.top_bar.set_activity_button_state(not is_visible)

    def _on_toggle_pause(self):
        is_now_paused = self.engine.toggle_pause()
        self.activity_panel.set_paused_state(is_now_paused)

    def _on_message(self, data: dict):
        role = data.get("role", "assistant")
        text = data.get("content", "")
        self.chat_page.add_message(role, text)

    def _on_step_started(self, data: dict):
        self.status_bar.set_engine_state(f"Working: {data.get('tool_name', 'action')}")
        self.activity_panel.on_step_started(
            data.get("step", 1),
            data.get("tool_name", "tool"),
            data.get("elapsed", 0.0),
        )

    def _on_step_finished(self, data: dict):
        self.activity_panel.on_step_finished(
            data.get("step", 1),
            data.get("tool_name", "tool"),
            data.get("success", True),
            str(data.get("result", "")),
            data.get("duration", 0.0),
        )

    def _on_status(self, data: dict):
        st = data.get("status", "SUCCESS")
        msg = data.get("message", "")
        self.status_bar.set_engine_state(self.engine.state)

    def _on_provider_changed(self, data: dict):
        self.top_bar.update_provider_info(data.get("provider", ""), data.get("model", ""))

    def _on_quota_updated(self, data: dict):
        self.top_bar.update_quota(data.get("requests_today", 0), data.get("quota_per_day", 1000))

    def _on_approval_requested(self, data: dict):
        self.status_bar.set_engine_state("Waiting for approval")
        dlg = ApprovalDialog(
            request_id=data.get("request_id", ""),
            action_type=data.get("action_type", ""),
            details=data.get("details", {}),
            risk_level=data.get("risk_level", "medium"),
            target=data.get("target", ""),
            message=data.get("message", ""),
            timeout_seconds=data.get("timeout", 60),
            parent=self,
        )
        dlg.decision_made.connect(
            lambda approved, always: self.engine.approve(data.get("request_id"), approved, always)
        )
        dlg.exec()

    def _on_error(self, data: dict):
        err = data.get("error", "Engine error")
        self.error_msg_label.setText(f"Engine Alert: {err}")
        self.error_banner.show()
        self.status_bar.set_engine_state("Engine Error")

    def _on_restart_engine_clicked(self):
        self.error_banner.hide()
        self.engine.restart()
        self.status_bar.set_engine_state(self.engine.state)
