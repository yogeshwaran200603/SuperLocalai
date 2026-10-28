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

import os
from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
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
    QSystemTrayIcon,
    QApplication,
)
from superlocal.ui.theme import Colors, get_stylesheet
from superlocal.ui.widgets.sidebar import Sidebar
from superlocal.ui.widgets.top_bar import TopBar
from superlocal.ui.widgets.status_bar import StatusBar
from superlocal.ui.widgets.activity_panel import ActivityPanel
from superlocal.ui.widgets.approval_dialog import ApprovalDialog
from superlocal.ui.widgets.quick_command import QuickCommandBar
from superlocal.ui.widgets.control_overlay import ControlOverlayPill
from superlocal.ui.widgets.tray import SuperLocalTrayIcon
from superlocal.ui.pages.chat_page import ChatPage
from superlocal.ui.pages.tasks_page import TasksPage
from superlocal.ui.pages.voice_page import VoicePage
from superlocal.ui.pages.games_page import GamesPage
from superlocal.ui.pages.optimizer_page import OptimizerPage
from superlocal.ui.pages.skills_page import SkillsPage
from superlocal.ui.pages.history_page import HistoryPage
from superlocal.ui.pages.settings_page import SettingsPage
from superlocal.ui.pages.wizard import is_first_run, SetupWizardDialog
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

        # Stacked Pages (Indices 0 to 7 matching Sidebar.NAV_ITEMS)
        self.page_stack = QStackedWidget(self)

        # 0: Chat
        self.chat_page = ChatPage(self)
        self.chat_page.submit_prompt.connect(self.engine.submit)
        self.chat_page.voice_toggle_requested.connect(lambda: self.sidebar.select_page(2))
        self.page_stack.addWidget(self.chat_page)

        # 1: Tasks (Autopilot)
        self.tasks_page = TasksPage(self)
        self.tasks_page.run_goal_requested.connect(
            lambda goal, dry: self.engine.submit(f"/auto --dry {goal}" if dry else f"/auto {goal}")
        )
        self.tasks_page.undo_requested.connect(lambda jid: self.engine.submit("/auto undo"))
        self.page_stack.addWidget(self.tasks_page)

        # 2: Voice
        self.voice_page = VoicePage(self)
        self.page_stack.addWidget(self.voice_page)

        # 3: Games (Poki + OpenFront)
        self.games_page = GamesPage(self)
        self.games_page.play_poki_requested.connect(
            lambda g, goal: self.engine.submit(f"/poki play {g} --goal '{goal}'" if goal else f"/poki play {g}")
        )
        self.games_page.stop_poki_requested.connect(lambda: self.engine.submit("/poki stop"))
        self.games_page.run_openfront_requested.connect(
            lambda url, strat: self.engine.submit(f"/openfront play --server '{url}'")
        )
        self.page_stack.addWidget(self.games_page)

        # 4: Optimizer
        self.optimizer_page = OptimizerPage(self)
        self.optimizer_page.scan_requested.connect(lambda: self.engine.submit("/optimize scan"))
        self.optimizer_page.clean_requested.connect(lambda cats: self.engine.submit("/optimize clean"))
        self.optimizer_page.undo_requested.connect(lambda: self.engine.submit("/optimize undo"))
        self.page_stack.addWidget(self.optimizer_page)

        # 5: Skills & Tools
        self.skills_page = SkillsPage(self)
        self.page_stack.addWidget(self.skills_page)

        # 6: History
        self.history_page = HistoryPage(self)
        self.page_stack.addWidget(self.history_page)

        # 7: Settings
        self.settings_page = SettingsPage(self)
        self.page_stack.addWidget(self.settings_page)

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

        # Stage 4: Quick Command Bar, Control Overlay Pill, Global Hotkeys, and System Tray
        self.quick_bar = QuickCommandBar(self)
        self.quick_bar.submitted.connect(self.engine.submit)

        self.control_pill = ControlOverlayPill(self)
        self.control_pill.stop_requested.connect(self.engine.stop)
        self.control_pill.pause_requested.connect(self._on_toggle_pause)

        # Global hotkeys within app window: Ctrl+Alt+Space, Ctrl+Alt+Q, Ctrl+Alt+P
        self.shortcut_quick = QShortcut(QKeySequence("Ctrl+Alt+Space"), self)
        self.shortcut_quick.activated.connect(self.quick_bar.show_centered)

        self.shortcut_stop = QShortcut(QKeySequence("Ctrl+Alt+Q"), self)
        self.shortcut_stop.activated.connect(self.engine.stop)

        self.shortcut_pause = QShortcut(QKeySequence("Ctrl+Alt+P"), self)
        self.shortcut_pause.activated.connect(self._on_toggle_pause)

        # System Tray
        self._quitting = False
        self.tray_icon = SuperLocalTrayIcon(self)
        self.tray_icon.restore_requested.connect(self._restore_from_tray)
        self.tray_icon.stop_requested.connect(self.engine.stop)
        self.tray_icon.quit_requested.connect(self._force_quit)
        if QSystemTrayIcon.isSystemTrayAvailable() and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.tray_icon.show()

        # Connect Qt event bridge to engine
        self._wire_engine_events()

        # First run check
        if (
            is_first_run()
            and os.environ.get("SUPERLOCAL_NO_WIZARD") != "1"
            and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
        ):
            QTimer.singleShot(150, self._show_first_run_wizard)

    def _show_first_run_wizard(self):
        wizard = SetupWizardDialog(self)
        wizard.exec()

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
        self.bridge.voice_state_updated.connect(self._on_voice_state)
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
        tool_name = data.get("tool_name", "action")
        self.status_bar.set_engine_state(f"Working: {tool_name}")
        self.activity_panel.on_step_started(
            data.get("step", 1),
            tool_name,
            data.get("elapsed", 0.0),
        )
        self.control_pill.update_step(tool_name)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.control_pill.show_pill()

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
        if self.engine.state in (EngineState.IDLE, EngineState.STOPPED):
            self.control_pill.hide()

    def _on_voice_state(self, data: dict):
        state = data.get("state", "idle")
        rms = data.get("rms", 0.0)
        self.voice_page.set_voice_state(state)
        self.voice_page.update_audio_level(rms)
        self.voice_page.update_transcripts(
            partial=data.get("partial", ""),
            final=data.get("final", ""),
            reply=data.get("reply", ""),
        )
        self.status_bar.set_mic_status(state == "listening")

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

    def _restore_from_tray(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _force_quit(self):
        self._quitting = True
        self.engine.stop()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        if hasattr(self, "control_pill"):
            self.control_pill.hide()
        if hasattr(self, "quick_bar"):
            self.quick_bar.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if not self._quitting and QSystemTrayIcon.isSystemTrayAvailable() and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "SuperLocal",
                "SuperLocal is running in the background. Click the tray icon to restore.",
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            self._force_quit()
            event.accept()
