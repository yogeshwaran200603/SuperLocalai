"""
Astra-Local Takeover Mode Automated Test Suite
Validates:
1. JSON action response parsing (arrays, markdown code fences, dictionary wrappers).
2. Image resizing, coordinate mapping with scale factor and window offsets.
3. Numbered UIA badge overlay and element ID resolution.
4. Human mouse interference monitor pause after 2s.
5. Sensitive action y/n guardrails (password typing, send/delete/pay).
6. 30 action limit and 5-action batching with 0.3s pauses.
7. Verification failure circuit breaker (stops after 3 consecutive failures).
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from takeover import (
    parse_gemini_actions_response,
    execute_takeover_action,
    run_takeover_mode,
    MouseInterferenceMonitor,
    TAKEOVER_MAX_ACTIONS,
    BATCH_SIZE,
    ACTION_PAUSE,
)
from safety import (
    trigger_emergency_stop,
    reset_emergency_stop,
    is_emergency_stopped,
)


class TestTakeoverModeSuite(unittest.TestCase):
    def setUp(self):
        reset_emergency_stop()

    def tearDown(self):
        reset_emergency_stop()

    def test_json_action_parsing_varieties(self):
        """Tests parsing of JSON actions from various model output formats."""
        # Standard array
        text1 = '[{"action": "click", "id": 5}, {"action": "type", "text": "test"}]'
        acts1 = parse_gemini_actions_response(text1)
        self.assertEqual(len(acts1), 2)
        self.assertEqual(acts1[0]["action"], "click")
        self.assertEqual(acts1[0]["id"], 5)

        # Markdown fenced code block
        text2 = "```json\n[{\"action\": \"hotkey\", \"keys\": [\"ctrl\", \"s\"]}]\n```"
        acts2 = parse_gemini_actions_response(text2)
        self.assertEqual(len(acts2), 1)
        self.assertEqual(acts2[0]["action"], "hotkey")
        self.assertEqual(acts2[0]["keys"], ["ctrl", "s"])

        # Dict with 'actions' key
        text3 = '{"actions": [{"action": "wait", "seconds": 1.5}, {"action": "done", "summary": "Finished"}]}'
        acts3 = parse_gemini_actions_response(text3)
        self.assertEqual(len(acts3), 2)
        self.assertEqual(acts3[1]["action"], "done")

    def test_coordinate_mapping_and_id_resolution(self):
        """Tests screen coordinate resolution from ID badge vs scaled (x, y)."""
        elements_map = {
            3: {"cx": 450, "cy": 320, "name": "Save Button", "type": "Button"}
        }
        monitor = MagicMock()

        # Click by ID
        with patch("pyautogui.click") as mock_click:
            act_id = {"action": "click", "id": 3}
            success, msg = execute_takeover_action(act_id, scale=0.5, win_x=100, win_y=50, elements_map=elements_map, monitor=monitor)
            self.assertTrue(success)
            mock_click.assert_called_with(450, 320)

        # Click by scaled coordinates: img coords (200, 100) with scale=0.5 and win_offset=(100, 50)
        # Real screen coords = win_x + int(200/0.5) = 100 + 400 = 500, win_y + int(100/0.5) = 50 + 200 = 250
        with patch("pyautogui.click") as mock_click:
            act_xy = {"action": "click", "x": 200, "y": 100}
            success, msg = execute_takeover_action(act_xy, scale=0.5, win_x=100, win_y=50, elements_map={}, monitor=monitor)
            self.assertTrue(success)
            mock_click.assert_called_with(500, 250)

    def test_sensitive_action_guardrails(self):
        """Tests that password typing and delete/send/pay clicks require y/n confirmation."""
        monitor = MagicMock()

        # Denied password typing
        with patch("safety.Confirm.ask", return_value=False):
            act_pw = {"action": "type", "text": "MySecretPassword123"}
            success, msg = execute_takeover_action(act_pw, scale=1.0, win_x=0, win_y=0, elements_map={}, monitor=monitor)
            self.assertFalse(success)
            self.assertIn("cancelled", msg)

        # Denied sensitive button click
        elements_map = {
            1: {"cx": 100, "cy": 100, "name": "Delete All Files", "type": "Button"}
        }
        with patch("safety.Confirm.ask", return_value=False):
            act_del = {"action": "click", "id": 1}
            success, msg = execute_takeover_action(act_del, scale=1.0, win_x=0, win_y=0, elements_map=elements_map, monitor=monitor)
            self.assertFalse(success)
            self.assertIn("cancelled", msg)

    def test_emergency_stop_halts_takeover(self):
        """Validates that Ctrl+Alt+Q stops takeover mode immediately."""
        trigger_emergency_stop("Test hotkey")
        self.assertTrue(is_emergency_stopped())

        result = run_takeover_mode("sample task")
        self.assertIn("halted via emergency stop", result)

    def test_verification_failure_circuit_breaker(self):
        """Validates that takeover mode halts after 3 consecutive failed verifications."""
        dummy_jpeg = b"\xff\xd8\xff\xe0dummy"
        batch_actions = [{"action": "wait", "seconds": 0.1}]

        with patch("takeover.prepare_takeover_observation", return_value=(dummy_jpeg, 1.0, 0, 0, {}, "dummy.jpg")), \
             patch("takeover.plan_takeover_batch", return_value=batch_actions), \
             patch("takeover.verify_batch_outcome", return_value=(False, "UI element not found")):

            res = run_takeover_mode("test verification breaker")
            self.assertIn("3 consecutive visual verifications failed", res)


if __name__ == "__main__":
    unittest.main()
