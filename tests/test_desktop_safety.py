"""
Astra-Local Comprehensive Desktop Safety Test Suite
Validates all 7 desktop safety controls:
1. Global hotkey (Ctrl+Alt+Q) emergency stop engine via keyboard in background thread.
2. PyAutoGUI FAILSAFE=True and 0.5s pause enforcement, with FailSafeException recovery.
3. Pre-session warning ('Astra will control your mouse and keyboard...') and (y/n) prompt.
4. Post-action visual verification loop with 3-failure cap and emergency halt.
5. Sensitive field (password) and button (send/pay/delete/confirm) interactive y/n guardrails.
6. Configurable cap at 25 desktop actions per task (MAX_DESKTOP_ACTIONS).
7. Screenshot saving to logs/screens/ with timestamps and 7-day automatic cleanup.
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pyautogui
from config import SCREENS_DIR, MAX_DESKTOP_ACTIONS
from safety import (
    trigger_emergency_stop,
    is_emergency_stopped,
    reset_emergency_stop,
    start_emergency_stop_listener,
    check_desktop_session_permission,
    is_desktop_session_approved,
    set_desktop_session_approved,
    reset_desktop_session,
    confirm_sensitive_desktop_action,
    is_sensitive_target_or_text,
)
from tools.desktop import (
    desktop_screenshot,
    desktop_click,
    desktop_type,
    desktop_hotkey,
    desktop_focus_window,
    cleanup_old_screenshots,
    get_desktop_action_count,
    reset_desktop_action_count,
    get_verification_failures,
    reset_verification_failures,
    verify_desktop_action_result,
)


class TestDesktopSafetySuite(unittest.TestCase):
    def setUp(self):
        reset_emergency_stop()
        reset_desktop_session()
        reset_desktop_action_count()
        reset_verification_failures()

    def tearDown(self):
        reset_emergency_stop()
        reset_desktop_session()
        reset_desktop_action_count()
        reset_verification_failures()

    # =========================================================================
    # Requirement 1: Global Hotkey (Ctrl+Alt+Q) & Emergency Stop
    # =========================================================================
    def test_emergency_stop_mechanism(self):
        """Validates that triggering emergency stop immediately blocks desktop actions."""
        start_emergency_stop_listener()
        self.assertFalse(is_emergency_stopped())

        # Trigger emergency stop
        trigger_emergency_stop(source="Test Hotkey")
        self.assertTrue(is_emergency_stopped())

        # Attempting desktop actions while stopped must immediately fail
        set_desktop_session_approved(True)
        res_click = desktop_click(x=100, y=100)
        self.assertFalse(res_click["success"])
        self.assertIn("Emergency stop", res_click["error"])

        res_type = desktop_type("hello")
        self.assertFalse(res_type["success"])
        self.assertIn("Emergency stop", res_type["error"])

        res_shot = desktop_screenshot()
        self.assertFalse(res_shot["success"])
        self.assertIn("Emergency stop", res_shot["error"])

        # Resetting must restore normal state
        reset_emergency_stop()
        self.assertFalse(is_emergency_stopped())

    # =========================================================================
    # Requirement 2: PyAutoGUI FAILSAFE=True & 0.5s Pause
    # =========================================================================
    def test_pyautogui_safety_settings_and_failsafe_handling(self):
        """Validates PyAutoGUI FAILSAFE is True, PAUSE is 0.5s, and corner aborts set emergency stop."""
        self.assertTrue(pyautogui.FAILSAFE, "FAILSAFE must remain True")
        self.assertEqual(pyautogui.PAUSE, 0.5, "PAUSE must be 0.5s between actions")

        # Simulate FailSafeException when mouse is dragged to corner (0,0)
        set_desktop_session_approved(True)
        with patch("pyautogui.click", side_effect=pyautogui.FailSafeException("Corner reached")):
            res = desktop_click(x=0, y=0)
            self.assertFalse(res["success"])
            self.assertIn("FailSafe triggered", res["error"])
            self.assertTrue(is_emergency_stopped(), "FailSafe must trigger emergency stop")

    # =========================================================================
    # Requirement 3: Pre-Session Warning and y/n Confirmation
    # =========================================================================
    def test_pre_session_warning_and_confirmation(self):
        """Validates that any desktop session requires pre-approval with the mandatory safety text."""
        self.assertFalse(is_desktop_session_approved())

        # User denies desktop control
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = desktop_click(x=200, y=200)
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "DENIED")
            self.assertFalse(is_desktop_session_approved())

        # User approves desktop control
        with patch("rich.prompt.Confirm.ask", return_value=True), \
             patch("pyautogui.click", return_value=None), \
             patch("tools.desktop.desktop_screenshot", return_value={"success": True, "path": "dummy.png"}), \
             patch("tools.desktop.verify_desktop_action_result", return_value=(True, "Verified")):
            res = desktop_click(x=200, y=200)
            self.assertTrue(res["success"])
            self.assertTrue(is_desktop_session_approved())

    # =========================================================================
    # Requirement 4: Visual Verification & Stop After 3 Failures
    # =========================================================================
    def test_visual_verification_and_three_failure_cap(self):
        """Validates post-action screenshot verification stops desktop automation after 3 failures."""
        set_desktop_session_approved(True)

        with patch("pyautogui.click", return_value=None), \
             patch("tools.desktop.desktop_screenshot", return_value={"success": True, "path": "dummy.png"}), \
             patch("tools.desktop.verify_desktop_action_result", return_value=(False, "Element not changed")):

            # 1st failed verification
            res1 = desktop_click(x=10, y=10)
            self.assertTrue(res1["success"])
            self.assertEqual(get_verification_failures(), 1)

            # 2nd failed verification
            res2 = desktop_click(x=20, y=20)
            self.assertTrue(res2["success"])
            self.assertEqual(get_verification_failures(), 2)

            # 3rd failed verification -> Must halt and set emergency stop
            res3 = desktop_click(x=30, y=30)
            self.assertFalse(res3["success"])
            self.assertIn("3 consecutive visual verifications failed", res3["error"])
            self.assertTrue(is_emergency_stopped())

    def test_visual_verification_recovery_resets_counter(self):
        """Validates that a successful verification resets failure counter."""
        set_desktop_session_approved(True)

        with patch("pyautogui.click", return_value=None), \
             patch("tools.desktop.desktop_screenshot", return_value={"success": True, "path": "dummy.png"}):

            # Fail once
            with patch("tools.desktop.verify_desktop_action_result", return_value=(False, "Failed")):
                desktop_click(x=10, y=10)
                self.assertEqual(get_verification_failures(), 1)

            # Succeed next -> resets to 0
            with patch("tools.desktop.verify_desktop_action_result", return_value=(True, "Success")):
                desktop_click(x=10, y=10)
                self.assertEqual(get_verification_failures(), 0)

    # =========================================================================
    # Requirement 5: Sensitive Guardrails (Passwords, Send, Pay, Delete, Confirm)
    # =========================================================================
    def test_sensitive_keyword_detection(self):
        """Validates keyword detection for passwords and sensitive buttons."""
        self.assertTrue(is_sensitive_target_or_text("Enter your password"))
        self.assertTrue(is_sensitive_target_or_text("Click 'Confirm Payment'"))
        self.assertTrue(is_sensitive_target_or_text("Delete account permanently"))
        self.assertTrue(is_sensitive_target_or_text("Send transaction"))
        self.assertFalse(is_sensitive_target_or_text("Open Notepad"))

    def test_password_field_typing_confirmation(self):
        """Validates typing into password fields requires interactive y/n confirmation."""
        set_desktop_session_approved(True)

        # Denied password typing
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = desktop_type("SecretPass123!", target_description="User password field")
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "USER_DENIED")

        # Approved password typing
        with patch("rich.prompt.Confirm.ask", return_value=True), \
             patch("pyautogui.write", return_value=None), \
             patch("tools.desktop.desktop_screenshot", return_value={"success": True, "path": "dummy.png"}), \
             patch("tools.desktop.verify_desktop_action_result", return_value=(True, "Verified")):
            res = desktop_type("SecretPass123!", target_description="User password field")
            self.assertTrue(res["success"])

    def test_sensitive_button_click_confirmation(self):
        """Validates clicking send/pay/delete/confirm buttons requires interactive y/n confirmation."""
        set_desktop_session_approved(True)

        # Denied click on Delete button
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = desktop_click(x=150, y=150, element_description="Delete Database Button")
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "USER_DENIED")

        # Denied click on Pay button
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = desktop_click(x=200, y=200, element_description="Pay $500 Now")
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "USER_DENIED")

    def test_enter_key_on_sensitive_element_confirmation(self):
        """Validates pressing Enter on send/pay/delete/confirm buttons requires y/n confirmation."""
        set_desktop_session_approved(True)

        # Denied Enter on Confirm button
        with patch("rich.prompt.Confirm.ask", return_value=False):
            res = desktop_hotkey(["enter"], target_description="Confirm Purchase button")
            self.assertFalse(res["success"])
            self.assertEqual(res.get("status"), "USER_DENIED")

        # Approved Enter on Confirm button
        with patch("rich.prompt.Confirm.ask", return_value=True), \
             patch("pyautogui.hotkey", return_value=None):
            res = desktop_hotkey(["enter"], target_description="Confirm Purchase button")
            self.assertTrue(res["success"])

    # =========================================================================
    # Requirement 6: Cap at 25 Desktop Actions
    # =========================================================================
    def test_desktop_action_limit_capping(self):
        """Validates that a task cannot exceed MAX_DESKTOP_ACTIONS (25)."""
        self.assertEqual(MAX_DESKTOP_ACTIONS, 25)
        set_desktop_session_approved(True)

        with patch("pyautogui.click", return_value=None), \
             patch("tools.desktop.desktop_screenshot", return_value={"success": True, "path": "dummy.png"}), \
             patch("tools.desktop.verify_desktop_action_result", return_value=(True, "Verified")):

            # Perform 25 actions (should all succeed)
            for i in range(25):
                res = desktop_click(x=10, y=10)
                self.assertTrue(res["success"], f"Action {i+1} should succeed")

            self.assertEqual(get_desktop_action_count(), 25)

            # The 26th action must be rejected
            res_exceeded = desktop_click(x=10, y=10)
            self.assertFalse(res_exceeded["success"])
            self.assertIn("Maximum desktop actions limit reached", res_exceeded["error"])

            # Resetting allows new actions
            reset_desktop_action_count()
            self.assertEqual(get_desktop_action_count(), 0)
            res_after_reset = desktop_click(x=10, y=10)
            self.assertTrue(res_after_reset["success"])

    # =========================================================================
    # Requirement 7: Screenshot Timestamping & 7-Day Retention Cleanup
    # =========================================================================
    def test_screenshot_storage_and_retention_cleanup(self):
        """Validates screenshots are stored in logs/screens/ and files older than 7 days are pruned."""
        set_desktop_session_approved(True)
        SCREENS_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Capture real/fallback screenshot
        res = desktop_screenshot()
        self.assertTrue(res["success"])
        shot_path = Path(res["path"])
        self.assertTrue(shot_path.exists())
        self.assertEqual(shot_path.parent.resolve(), SCREENS_DIR.resolve())
        self.assertTrue(shot_path.name.startswith("screenshot_"))

        # 2. Create dummy screenshot older than 8 days
        old_file = SCREENS_DIR / "screenshot_old_dummy_test.png"
        old_file.write_text("dummy old image content")
        eight_days_ago = time.time() - (8 * 86400)
        os.utime(old_file, (eight_days_ago, eight_days_ago))

        # Create dummy recent screenshot (1 day old)
        recent_file = SCREENS_DIR / "screenshot_recent_dummy_test.png"
        recent_file.write_text("dummy recent image content")
        one_day_ago = time.time() - (1 * 86400)
        os.utime(recent_file, (one_day_ago, one_day_ago))

        # Run cleanup with 7-day retention
        deleted = cleanup_old_screenshots(days=7)
        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(old_file.exists(), "Files older than 7 days must be deleted")
        self.assertTrue(recent_file.exists(), "Files newer than 7 days must be retained")

        # Clean up test dummy
        if recent_file.exists():
            recent_file.unlink()


if __name__ == "__main__":
    unittest.main()
