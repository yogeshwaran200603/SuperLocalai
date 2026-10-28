"""
Unit tests for Phase 2: Local-First Rules & Slash Commands (Zero Model Calls)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, MagicMock
from agent import try_local_first_execution
from openfront import validate_openfront_url, handle_openfront_command


def test_open_app_zero_model_calls():
    with patch("tools.shell.subprocess.Popen") as mock_popen:
        res = try_local_first_execution("open notepad")
        assert res is not None
        assert "notepad" in res.lower()


def test_open_folder_zero_model_calls():
    with patch("tools.shell.subprocess.Popen") as mock_popen:
        res = try_local_first_execution("open desktop")
        assert res is not None
        assert "desktop" in res.lower()


def test_open_website_zero_model_calls():
    with patch("webbrowser.open") as mock_web:
        res = try_local_first_execution("open youtube")
        assert res is not None
        assert "youtube" in res.lower()


def test_discord_shortcut_zero_model_calls():
    with patch("tools.shell.subprocess.Popen"):
        res = try_local_first_execution("open discord and go to my server")
        assert res is not None
        assert "discord" in res.lower()


def test_poki_play_routing_zero_model_calls():
    with patch("poki.handle_poki_command", return_value="[Poki] Routed game"):
        res1 = try_local_first_execution("play little master cricket")
        assert res1 == "[Poki] Routed game"

        res2 = try_local_first_execution("play the game")
        assert res2 == "[Poki] Routed game"

        res3 = try_local_first_execution("can you play cricket on poki")
        assert res3 == "[Poki] Routed game"


def test_slash_commands_zero_model_calls():
    # /help
    assert "locally" in try_local_first_execution("/help")
    # /health
    assert "health" in try_local_first_execution("/health")
    # /selftest
    with patch("selftest.run_selftest", return_value=(True, [])):
        assert "Self-test passed" in try_local_first_execution("/selftest")
    # /stop
    with patch("safety.trigger_emergency_stop") as mock_stop:
        assert "Emergency stop" in try_local_first_execution("/stop")
        assert mock_stop.called


def test_openfront_localhost_guard():
    # Non-localhost origin must be rejected
    valid_remote, msg_remote = validate_openfront_url("https://openfront.io/game")
    assert valid_remote is False
    assert "prohibited" in msg_remote.lower() or "not a local host" in msg_remote.lower()

    valid_ip, msg_ip = validate_openfront_url("http://192.168.1.50:8080")
    assert valid_ip is False

    # Localhost origin must be accepted
    valid_local1, _ = validate_openfront_url("http://localhost:8080")
    assert valid_local1 is True

    valid_local2, _ = validate_openfront_url("http://127.0.0.1:3000")
    assert valid_local2 is True
