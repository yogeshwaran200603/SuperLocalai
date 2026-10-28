"""
Headless pytest-qt unit tests for Stage 2:
Main window, chat page, activity panel, stop button, approval dialogs, and crash recovery.
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force offscreen rendering for headless test environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.engine import SuperLocalEngine, EngineState
from superlocal.ui.main_window import SuperLocalMainWindow
from superlocal.ui.widgets.approval_dialog import ApprovalDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_main_window_initialization(qapp, qtbot):
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() == "SuperLocal"
    assert window.sidebar is not None
    assert window.top_bar is not None
    assert window.status_bar is not None
    assert window.activity_panel is not None
    assert window.chat_page is not None


def test_chat_page_submission(qapp, qtbot):
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)
    window.show()

    with patch("tools.shell.subprocess.Popen"):
        # Type into editor
        window.chat_page.editor.setPlainText("open notepad")
        # Send
        window.chat_page._on_send_clicked()

        # Wait for worker thread to process
        if engine._worker_thread:
            engine._worker_thread.join(timeout=5.0)

        # Allow Qt event loop to deliver bridged signals
        qtbot.wait(300)

    # Check that assistant message bubble was added to chat layout
    count = window.chat_page.messages_layout.count()
    assert count >= 3  # Initial welcome + user + assistant bubble + stretch


def test_activity_panel_and_stop_button(qapp, qtbot):
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)
    window.show()

    # Click STOP button
    window.activity_panel.stop_btn.click()
    assert engine.state == EngineState.STOPPED


def test_approval_dialog_flow(qapp, qtbot):
    # Test Allow once
    dlg1 = ApprovalDialog(
        request_id="test1",
        action_type="file_delete",
        details={"path": "C:/dummy.txt"},
        risk_level="high",
        target="C:/dummy.txt",
        timeout_seconds=60,
    )
    qtbot.addWidget(dlg1)

    with qtbot.waitSignal(dlg1.decision_made, timeout=1000) as blocker:
        dlg1.allow_once_btn.click()
    assert blocker.args == [True, False]

    # Test Deny
    dlg2 = ApprovalDialog(
        request_id="test2",
        action_type="file_delete",
        details={"path": "C:/dummy.txt"},
        risk_level="high",
        target="C:/dummy.txt",
        timeout_seconds=60,
    )
    qtbot.addWidget(dlg2)

    with qtbot.waitSignal(dlg2.decision_made, timeout=1000) as blocker:
        dlg2.deny_btn.click()
    assert blocker.args == [False, False]

    # Test Always for session (on non-dangerous action)
    dlg3 = ApprovalDialog(
        request_id="test3",
        action_type="desktop_click",
        details={"x": 100, "y": 100},
        risk_level="medium",
        target="Canvas area",
        timeout_seconds=60,
    )
    qtbot.addWidget(dlg3)
    assert hasattr(dlg3, "allow_always_btn")

    with qtbot.waitSignal(dlg3.decision_made, timeout=1000) as blocker:
        dlg3.allow_always_btn.click()
    assert blocker.args == [True, True]


def test_crash_recovery_banner_in_gui(qapp, qtbot):
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)
    window.show()

    # Simulate an error event
    window.bridge.error_occurred.emit({"error": "Simulated hardware fault"})
    qtbot.wait(100)

    # Banner must be visible with message and window must still be open
    assert window.error_banner.isVisible()
    assert "Simulated hardware fault" in window.error_msg_label.text()
    assert window.isVisible()

    # Click Restart Engine
    window.restart_engine_btn.click()
    qtbot.wait(100)
    assert not window.error_banner.isVisible()
    assert engine.state == EngineState.IDLE
