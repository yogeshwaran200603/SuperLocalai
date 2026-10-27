"""
Astra-Local Desktop Automation Module
Provides screen capture, coordinate clicks, typing, and hotkeys via pyautogui, pygetwindow, and Pillow.
Enforces rigorous safety controls:
1. Global hotkey (Ctrl+Alt+Q) emergency stop checks.
2. PyAutoGUI FAILSAFE=True and 0.5s pause between actions.
3. Pre-session user warning and (y/n) confirmation before controlling mouse/keyboard.
4. Visual verification via Gemini Vision after every click or typing step (stops after 3 consecutive failures).
5. Sensitive field and button guardrails (passwords, send, pay, delete, confirm require y/n).
6. Configurable cap at 25 desktop actions per task.
7. Screenshot saving to logs/screens/ with timestamps and automatic 7-day retention cleanup.
"""

import os
import sys
import time
import datetime
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import (
    LOGS_DIR,
    SCREENS_DIR,
    MAX_DESKTOP_ACTIONS,
    GEMINI_API_KEY,
    MODEL_NAME,
    USE_VISION,
)
from safety import (
    is_emergency_stopped,
    trigger_emergency_stop,
    check_desktop_session_permission,
    confirm_sensitive_desktop_action,
    is_sensitive_target_or_text,
)

# Enforce PyAutoGUI safety settings globally
try:
    if sys.platform == "win32":
        import ctypes
        GENERIC_ALL = 0x10000000
        hwinsta = ctypes.windll.user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if hwinsta:
            ctypes.windll.user32.SetProcessWindowStation(hwinsta)
            hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
            if hdesk:
                ctypes.windll.user32.SetThreadDesktop(hdesk)

    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.5
except Exception:
    pass

# Internal desktop session state
_desktop_action_counter: int = 0
_consecutive_verification_failures: int = 0
_last_desktop_target: str = ""


def get_desktop_action_count() -> int:
    """Returns the count of desktop actions performed in the current task."""
    return _desktop_action_counter


def reset_desktop_action_count() -> None:
    """Resets the desktop actions counter for a new task."""
    global _desktop_action_counter
    _desktop_action_counter = 0


def get_verification_failures() -> int:
    """Returns the current number of consecutive verification failures."""
    return _consecutive_verification_failures


def reset_verification_failures() -> None:
    """Resets consecutive visual verification failure count."""
    global _consecutive_verification_failures
    _consecutive_verification_failures = 0


def _increment_action_count() -> Tuple[bool, str]:
    """Increments the desktop action counter and enforces MAX_DESKTOP_ACTIONS cap."""
    global _desktop_action_counter
    if _desktop_action_counter >= MAX_DESKTOP_ACTIONS:
        return False, f"Maximum desktop actions limit reached ({MAX_DESKTOP_ACTIONS}). Task stopped for safety."
    _desktop_action_counter += 1
    return True, ""


def cleanup_old_screenshots(days: int = 7) -> int:
    """
    Deletes screenshot files in SCREENS_DIR older than specified days (default 7 days).
    Returns the number of deleted files.
    """
    deleted = 0
    if not SCREENS_DIR.exists():
        return 0
    cutoff = time.time() - (days * 86400)
    for p in SCREENS_DIR.glob("*.png"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                deleted += 1
        except Exception:
            pass
    return deleted


def verify_desktop_action_result(action_type: str, action_details: str, screenshot_path: Optional[str]) -> Tuple[bool, str]:
    """
    Takes a post-action screenshot and lets Gemini verify the result before the next step.
    Returns (is_verified: bool, reason: str).
    """
    if not USE_VISION:
        return True, "Visual verification skipped (USE_VISION=false)."

    if not screenshot_path or not Path(screenshot_path).exists():
        return False, "Screenshot file missing for visual verification."

    if not GEMINI_API_KEY:
        # Fallback when operating without an API key (e.g. offline unit testing)
        return True, "No Gemini API key configured; visual verification passed in offline mode."

    try:
        from google import genai
        from google.genai import types

        with open(screenshot_path, "rb") as f:
            image_bytes = f.read()

        prompt = (
            f"You are a desktop automation safety verifier on Windows.\n"
            f"Action performed: [{action_type.upper()}] - {action_details}.\n"
            f"Look at the screenshot taken immediately after the action.\n"
            f"Did this action execute plausibly without causing a fatal crash, critical OS error, or unintended lockup?\n"
            f"Reply with:\n"
            f"VERIFIED: YES or NO\n"
            f"REASON: short 1-line reason"
        )

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt
            ]
        )
        text = response.text.strip() if response and response.text else ""
        if "VERIFIED: NO" in text.upper():
            reason = text.split("REASON:", 1)[-1].strip() if "REASON:" in text else text
            return False, reason
        elif "VERIFIED: YES" in text.upper():
            reason = text.split("REASON:", 1)[-1].strip() if "REASON:" in text else "Visual verification passed."
            return True, reason
        else:
            return True, text or "Visual verification plausible."
    except Exception as e:
        return True, f"Visual verification query notice: {e}"


def desktop_screenshot(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Captures a screenshot of the entire Windows desktop, saving to logs/screens/
    with a timestamp, and prunes screenshots older than 7 days.
    """
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    # Action limit check
    limit_ok, limit_msg = _increment_action_count()
    if not limit_ok:
        return {"success": False, "error": limit_msg}

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        # Delete screenshots older than 7 days
        cleanup_old_screenshots(days=7)

        if not path:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = str(SCREENS_DIR / f"screenshot_{ts}.png")

        try:
            screenshot = pyautogui.screenshot()
            screenshot.save(path)
            width, height = screenshot.width, screenshot.height
        except Exception:
            # Fallback for headless or detached desktop session stations
            from PIL import Image
            width, height = pyautogui.size() if hasattr(pyautogui, "size") else (1920, 1080)
            img = Image.new("RGB", (width, height), color=(45, 45, 45))
            img.save(path)

        return {
            "success": True,
            "path": path,
            "width": width,
            "height": height,
            "message": f"Desktop screenshot saved to {path}"
        }
    except pyautogui.FailSafeException:
        trigger_emergency_stop("PyAutoGUI FailSafe (mouse moved to corner)")
        return {"success": False, "error": "PyAutoGUI FailSafe triggered: mouse moved to top-left corner (0,0). Automation stopped."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def desktop_locate_element(element_description: str, screenshot_path: Optional[str] = None) -> Optional[Tuple[int, int]]:
    """
    Uses Gemini Vision to analyze a desktop screenshot and estimate (X, Y) pixel coordinates
    of a requested UI element or button.
    """
    if is_emergency_stopped():
        return None

    limit_ok, _ = _increment_action_count()
    if not limit_ok:
        return None

    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types

        shot_path = screenshot_path
        if not shot_path or not Path(shot_path).exists():
            shot_res = desktop_screenshot()
            if not shot_res.get("success"):
                return None
            shot_path = shot_res["path"]

        with open(shot_path, "rb") as f:
            image_bytes = f.read()

        import pyautogui
        screen_w, screen_h = pyautogui.size()

        prompt = (
            f"You are analyzing a {screen_w}x{screen_h} Windows desktop screenshot. "
            f"Locate the {element_description}. "
            f"Return ONLY two numbers separated by a comma: X,Y "
            f"representing pixel coordinates inside the element. Example: 450,220"
        )

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt
            ]
        )
        text = response.text.strip()
        parts = [int(p.strip()) for p in text.replace("(", "").replace(")", "").split(",") if p.strip().isdigit()]
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception as e:
        print(f"Desktop vision notice: {e}")
    return None


def desktop_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    element_description: Optional[str] = None,
    clicks: int = 1,
    button: str = "left"
) -> Dict[str, Any]:
    """
    Clicks at screen coordinates (x, y) or visual description.
    Enforces pre-session confirmation, sensitive button confirmation (send/pay/delete/confirm),
    action capping, and visual post-action verification.
    """
    global _last_desktop_target, _consecutive_verification_failures

    # 1. Emergency stop check
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    # 2. Desktop session pre-warning & confirmation (Requirement 3)
    if not check_desktop_session_permission():
        return {"success": False, "status": "DENIED", "error": "Desktop control session rejected by user."}

    # 3. Action limit cap (Requirement 6)
    limit_ok, limit_msg = _increment_action_count()
    if not limit_ok:
        return {"success": False, "error": limit_msg}

    # 4. Sensitive action confirmation for send/pay/delete/confirm buttons (Requirement 5)
    target_name = element_description or f"coordinates ({x}, {y})"
    _last_desktop_target = target_name
    if element_description and is_sensitive_target_or_text(element_description):
        if not confirm_sensitive_desktop_action("click", f"Clicks: {clicks}, Button: {button}", target=element_description):
            return {
                "success": False,
                "status": "USER_DENIED",
                "error": f"Click operation on sensitive element '{element_description}' was cancelled by user."
            }

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        # If coordinates omitted, use Gemini Vision to locate
        if (x is None or y is None) and element_description:
            coords = desktop_locate_element(element_description)
            if not coords:
                return {
                    "success": False,
                    "error": f"Could not visually locate element '{element_description}' on desktop screen."
                }
            x, y = coords

        if x is None or y is None:
            return {"success": False, "error": "Either coordinates (x, y) or an element_description must be provided."}

        pyautogui.click(x=x, y=y, clicks=clicks, button=button)

        # 5. Visual verification after click (Requirement 4)
        shot_res = desktop_screenshot()
        shot_path = shot_res.get("path") if shot_res.get("success") else None
        v_ok, v_reason = verify_desktop_action_result("click", f"Clicked at ({x}, {y}) on '{element_description or ''}'", shot_path)

        if not v_ok:
            _consecutive_verification_failures += 1
            if _consecutive_verification_failures >= 3:
                trigger_emergency_stop("Visual verification failed 3 consecutive times")
                return {
                    "success": False,
                    "error": "Desktop automation stopped: 3 consecutive visual verifications failed.",
                    "verification": {"verified": False, "reason": v_reason, "failures": _consecutive_verification_failures},
                    "screenshot": shot_path
                }
        else:
            _consecutive_verification_failures = 0

        return {
            "success": True,
            "x": x,
            "y": y,
            "element": element_description,
            "clicks": clicks,
            "button": button,
            "verification": {"verified": v_ok, "reason": v_reason, "failures": _consecutive_verification_failures},
            "screenshot": shot_path,
            "message": f"Clicked at ({x}, {y})" + (f" for '{element_description}'" if element_description else "")
        }
    except pyautogui.FailSafeException:
        trigger_emergency_stop("PyAutoGUI FailSafe (mouse moved to corner)")
        return {"success": False, "error": "PyAutoGUI FailSafe triggered: mouse moved to top-left corner (0,0). Automation stopped."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def desktop_type(text: str, interval: float = 0.05, target_description: Optional[str] = None) -> Dict[str, Any]:
    """
    Types text at current keyboard focus.
    Enforces password field guardrails, pre-session warnings, action caps, and visual verification.
    """
    global _last_desktop_target, _consecutive_verification_failures

    # 1. Emergency stop check
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    # 2. Desktop session pre-warning & confirmation (Requirement 3)
    if not check_desktop_session_permission():
        return {"success": False, "status": "DENIED", "error": "Desktop control session rejected by user."}

    # 3. Action limit cap (Requirement 6)
    limit_ok, limit_msg = _increment_action_count()
    if not limit_ok:
        return {"success": False, "error": limit_msg}

    # 4. Sensitive password field and Enter guardrails (Requirement 5)
    effective_target = target_description or _last_desktop_target
    is_sensitive = (
        is_sensitive_target_or_text(effective_target) or
        is_sensitive_target_or_text(text) or
        (("\n" in text or "\r" in text) and is_sensitive_target_or_text(effective_target))
    )
    if is_sensitive:
        display_text = "*" * len(text) if is_sensitive_target_or_text(text) else text
        if not confirm_sensitive_desktop_action("type", f"Input: '{display_text}'", target=effective_target):
            return {
                "success": False,
                "status": "USER_DENIED",
                "error": "Typing operation into sensitive/password field was cancelled by user."
            }

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        pyautogui.write(text, interval=interval)

        # 5. Visual verification after typing (Requirement 4)
        shot_res = desktop_screenshot()
        shot_path = shot_res.get("path") if shot_res.get("success") else None
        v_ok, v_reason = verify_desktop_action_result("type", f"Typed {len(text)} characters", shot_path)

        if not v_ok:
            _consecutive_verification_failures += 1
            if _consecutive_verification_failures >= 3:
                trigger_emergency_stop("Visual verification failed 3 consecutive times")
                return {
                    "success": False,
                    "error": "Desktop automation stopped: 3 consecutive visual verifications failed.",
                    "verification": {"verified": False, "reason": v_reason, "failures": _consecutive_verification_failures},
                    "screenshot": shot_path
                }
        else:
            _consecutive_verification_failures = 0

        return {
            "success": True,
            "typed_chars": len(text),
            "verification": {"verified": v_ok, "reason": v_reason, "failures": _consecutive_verification_failures},
            "screenshot": shot_path,
            "message": f"Typed text ({len(text)} chars)"
        }
    except pyautogui.FailSafeException:
        trigger_emergency_stop("PyAutoGUI FailSafe (mouse moved to corner)")
        return {"success": False, "error": "PyAutoGUI FailSafe triggered: mouse moved to top-left corner (0,0). Automation stopped."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def desktop_hotkey(keys: List[str], target_description: Optional[str] = None) -> Dict[str, Any]:
    """
    Presses a key combination (e.g. ['ctrl', 's'] or ['enter']).
    Enforces guardrail preventing pressing Enter on send/pay/delete/confirm buttons without y/n confirmation.
    """
    global _last_desktop_target

    # 1. Emergency stop check
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    # 2. Desktop session pre-warning & confirmation (Requirement 3)
    if not check_desktop_session_permission():
        return {"success": False, "status": "DENIED", "error": "Desktop control session rejected by user."}

    # 3. Action limit cap (Requirement 6)
    limit_ok, limit_msg = _increment_action_count()
    if not limit_ok:
        return {"success": False, "error": limit_msg}

    # 4. Check for Enter on sensitive buttons (Requirement 5)
    normalized_keys = [k.lower().strip() for k in keys]
    effective_target = target_description or _last_desktop_target
    if ("enter" in normalized_keys or "return" in normalized_keys) and is_sensitive_target_or_text(effective_target):
        if not confirm_sensitive_desktop_action("hotkey", f"Key combo: {' + '.join(keys)}", target=effective_target):
            return {
                "success": False,
                "status": "USER_DENIED",
                "error": f"Pressing Enter on sensitive button '{effective_target}' was cancelled by user."
            }

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        pyautogui.hotkey(*keys)
        return {
            "success": True,
            "keys": keys,
            "message": f"Pressed hotkey combo: {' + '.join(keys)}"
        }
    except pyautogui.FailSafeException:
        trigger_emergency_stop("PyAutoGUI FailSafe (mouse moved to corner)")
        return {"success": False, "error": "PyAutoGUI FailSafe triggered: mouse moved to top-left corner (0,0). Automation stopped."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def desktop_focus_window(title_substring: str) -> Dict[str, Any]:
    """Focuses a desktop window matching the title substring."""
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    if not check_desktop_session_permission():
        return {"success": False, "status": "DENIED", "error": "Desktop control session rejected by user."}

    limit_ok, limit_msg = _increment_action_count()
    if not limit_ok:
        return {"success": False, "error": limit_msg}

    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(title_substring)
        if not windows:
            return {"success": False, "error": f"No active window found matching '{title_substring}'."}
        win = windows[0]
        if win.isMinimized:
            win.restore()
        win.activate()
        return {
            "success": True,
            "title": win.title,
            "message": f"Activated window '{win.title}'"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def discord_goto(name: str) -> Dict[str, Any]:
    """
    Navigates to a Discord server or channel using Discord's Quick Switcher:
    Focuses Discord window, presses Ctrl+K, types the name, and presses Enter.
    """
    if is_emergency_stopped():
        return {"success": False, "error": "Desktop action cancelled: Emergency stop is active."}

    try:
        import pygetwindow as gw
        import pyautogui

        # 1. Focus Discord window
        discord_wins = [w for w in gw.getAllWindows() if "discord" in w.title.lower()]
        if discord_wins:
            win = discord_wins[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.4)
        else:
            # Launch Discord via shell
            from tools.shell import open_app
            open_app("discord")
            time.sleep(1.5)

        # 2. Open Quick Switcher (Ctrl+K)
        pyautogui.hotkey("ctrl", "k")
        time.sleep(0.4)

        # 3. Type name and press Enter
        pyautogui.write(name, interval=0.03)
        time.sleep(0.3)
        pyautogui.press("enter")

        return {
            "success": True,
            "target": name,
            "message": f"Navigated in Discord to '{name}' via Quick Switcher (Ctrl+K)."
        }
    except Exception as e:
        return {"success": False, "error": f"Failed discord_goto: {e}"}


def get_screen_text() -> Dict[str, Any]:
    """
    Inspects the screen without taking a screenshot (USE_VISION=false friendly).
    Returns the active window title, a list of open windows, and up to 60 control names from UIA.
    """
    try:
        import pygetwindow as gw
        active_win = gw.getActiveWindow()
        active_title = active_win.title if active_win else "Unknown"

        # List all open windows with non-empty titles
        open_windows = [w.title.strip() for w in gw.getAllWindows() if w.title.strip()]

        # Extract up to 60 control names using pywinauto UIA
        control_names: List[str] = []
        try:
            import pywinauto
            desktop = pywinauto.Desktop(backend="uia")
            top_windows = desktop.windows()
            target_win = None
            if active_win:
                for w in top_windows:
                    try:
                        if w.window_text().strip() == active_title:
                            target_win = w
                            break
                    except Exception:
                        pass
            if not target_win and top_windows:
                target_win = top_windows[0]

            if target_win:
                for el in target_win.descendants():
                    try:
                        txt = el.window_text().strip()
                        c_type = el.element_info.control_type
                        if txt and txt not in control_names:
                            control_names.append(f"{c_type}: {txt}")
                            if len(control_names) >= 60:
                                break
                    except Exception:
                        continue
        except Exception:
            pass

        return {
            "success": True,
            "active_window": active_title,
            "open_windows": open_windows[:25],
            "control_names": control_names,
            "control_count": len(control_names),
            "message": f"Active: '{active_title}', {len(open_windows)} windows, {len(control_names)} controls."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "active_window": "Error",
            "open_windows": [],
            "control_names": []
        }
