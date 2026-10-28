"""
Tests for SuperLocal Stage 4: Voice Page, System Tray, Hotkeys, and Control Overlay Pill
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Force offscreen Qt platform before creating QApplication
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from superlocal.ui.widgets.orb import VoiceOrb
from superlocal.ui.pages.voice_page import VoicePage
from superlocal.ui.widgets.quick_command import QuickCommandBar
from superlocal.ui.widgets.control_overlay import ControlOverlayPill
from superlocal.ui.widgets.tray import SuperLocalTrayIcon
from superlocal.ui.main_window import SuperLocalMainWindow
from core.engine import SuperLocalEngine, EngineState
from core.events import EventType


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_voice_orb_states(qapp):
    """Test VoiceOrb transitions and RMS level updates."""
    orb = VoiceOrb()
    assert orb.state == VoiceOrb.STATE_IDLE

    orb.set_state(VoiceOrb.STATE_LISTENING)
    assert orb.state == VoiceOrb.STATE_LISTENING

    orb.set_state(VoiceOrb.STATE_THINKING)
    assert orb.state == VoiceOrb.STATE_THINKING

    orb.set_state(VoiceOrb.STATE_SPEAKING)
    assert orb.state == VoiceOrb.STATE_SPEAKING

    orb.set_level(0.85)
    assert orb._rms_level == 0.85

    orb.set_level(1.5)  # Clamped to 1.0
    assert orb._rms_level == 1.0


def test_voice_page_ptt_and_transcripts(qapp, qtbot):
    """Test VoicePage push-to-talk and transcript updates."""
    page = VoicePage()
    qtbot.addWidget(page)

    with qtbot.waitSignal(page.push_to_talk_triggered, timeout=1000) as blocker:
        page.ptt_btn.pressed.emit()
    assert blocker.args == [True]
    assert page.orb.state == "listening"

    with qtbot.waitSignal(page.push_to_talk_triggered, timeout=1000) as blocker:
        page.ptt_btn.released.emit()
    assert blocker.args == [False]
    assert page.orb.state == "thinking"

    # Transcript updates
    page.update_transcripts(partial="open brow", final="open browser", reply="Opening Chrome for you.")
    assert "open browser" in page.final_label.text()
    assert "Opening Chrome" in page.reply_label.text()

    # Level bar update
    page.update_audio_level(0.5)
    assert page.level_bar.value() == 50


def test_quick_command_bar(qapp, qtbot):
    """Test QuickCommandBar submit and escape dismiss."""
    bar = QuickCommandBar()
    qtbot.addWidget(bar)

    bar.input_edit.setText("test command")
    with qtbot.waitSignal(bar.submitted, timeout=1000) as blocker:
        bar._on_submit()
    assert blocker.args == ["test command"]
    assert bar.isHidden()


def test_control_overlay_pill(qapp, qtbot):
    """Test ControlOverlayPill step card, pause and stop buttons."""
    pill = ControlOverlayPill()
    qtbot.addWidget(pill)
    pill.show()

    pill.update_step("shell_exec")
    assert pill.step_label.text() == "[shell_exec]"
    assert not pill.step_label.isHidden()

    with qtbot.waitSignal(pill.pause_requested, timeout=1000) as blocker:
        pill.pause_btn.click()
    assert blocker.signal_triggered

    pill.set_paused_state(True)
    assert "Paused" in pill.status_label.text()

    pill.set_paused_state(False)
    assert "in control" in pill.status_label.text()

    with qtbot.waitSignal(pill.stop_requested, timeout=1000) as blocker:
        pill.stop_btn.click()
    assert blocker.signal_triggered


def test_tray_icon_and_window_integration(qapp, qtbot):
    """Test SuperLocalTrayIcon and hotkeys in SuperLocalMainWindow."""
    engine = SuperLocalEngine()
    window = SuperLocalMainWindow(engine=engine)
    qtbot.addWidget(window)

    assert window.voice_page is not None
    assert window.quick_bar is not None
    assert window.control_pill is not None
    assert window.tray_icon is not None

    # Test Stop signal from tray
    window.tray_icon.stop_requested.emit()
    assert engine.state == EngineState.STOPPED

    # Test Voice event emission delivery to VoicePage
    engine.events.emit(EventType.VOICE_STATE, {
        "state": "speaking",
        "rms": 0.6,
        "reply": "All systems operational.",
    })
    qtbot.wait(200)

    assert window.voice_page.orb.state == "speaking"
    assert "All systems operational." in window.voice_page.reply_label.text()
