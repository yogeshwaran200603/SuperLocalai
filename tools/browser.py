"""
Astra-Local Browser Automation Module
Implements Playwright with a persistent user data directory (Chromium) so sessions,
logins, and cookies (like WhatsApp Web) persist across runs.
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from config import BROWSER_USER_DATA_DIR, LOGS_DIR

_playwright_instance = None
_browser_context = None
_current_page = None


def get_browser_page():
    """
    Returns an active Playwright page attached to the persistent user data directory.
    Launches non-headlessly so users can see the browser actions and authenticate (e.g. WhatsApp QR).
    """
    global _playwright_instance, _browser_context, _current_page
    from playwright.sync_api import sync_playwright

    if _current_page is not None and not _current_page.is_closed():
        return _current_page

    if _playwright_instance is None:
        _playwright_instance = sync_playwright().start()

    if _browser_context is None:
        # Launch persistent context
        _browser_context = _playwright_instance.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_USER_DATA_DIR),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )

    if len(_browser_context.pages) > 0:
        _current_page = _browser_context.pages[0]
    else:
        _current_page = _browser_context.new_page()

    return _current_page


def close_browser():
    """Closes the browser context and stops Playwright."""
    global _playwright_instance, _browser_context, _current_page
    try:
        if _browser_context:
            _browser_context.close()
        if _playwright_instance:
            _playwright_instance.stop()
    except Exception:
        pass
    finally:
        _browser_context = None
        _playwright_instance = None
        _current_page = None


def browser_goto(url: str) -> Dict[str, Any]:
    """Navigates to the specified URL."""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    try:
        page = get_browser_page()
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        status = response.status if response else 200
        title = page.title()
        return {
            "success": True,
            "url": url,
            "title": title,
            "status": status,
            "message": f"Navigated to {url} (Title: {title})"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def browser_click(selector: str) -> Dict[str, Any]:
    """Clicks on an element matching the given CSS or text selector."""
    try:
        page = get_browser_page()
        page.wait_for_selector(selector, timeout=10000)
        page.click(selector)
        return {"success": True, "selector": selector, "message": f"Clicked element '{selector}'"}
    except Exception as e:
        return {"success": False, "selector": selector, "error": str(e)}


def browser_type(selector: str, text: str) -> Dict[str, Any]:
    """Types text into an input field or contenteditable element."""
    try:
        page = get_browser_page()
        page.wait_for_selector(selector, timeout=10000)
        page.fill(selector, "")
        page.type(selector, text, delay=30)
        return {"success": True, "selector": selector, "message": f"Typed text into '{selector}'"}
    except Exception as e:
        return {"success": False, "selector": selector, "error": str(e)}


def browser_press(selector: str, key: str) -> Dict[str, Any]:
    """Presses a keyboard key on the selected element."""
    try:
        page = get_browser_page()
        page.press(selector, key)
        return {"success": True, "key": key, "message": f"Pressed key '{key}' on '{selector}'"}
    except Exception as e:
        return {"success": False, "key": key, "error": str(e)}


def browser_read_text(selector: str = "body") -> Dict[str, Any]:
    """Extracts text content from the page or a specific selector."""
    try:
        page = get_browser_page()
        text = page.locator(selector).inner_text(timeout=5000)
        # Cap text to prevent token explosion
        return {
            "success": True,
            "selector": selector,
            "text": text[:4000],
            "total_length": len(text)
        }
    except Exception as e:
        return {"success": False, "selector": selector, "error": str(e)}


def browser_screenshot(path: Optional[str] = None) -> Dict[str, Any]:
    """Takes a screenshot of the current browser page."""
    try:
        page = get_browser_page()
        if not path:
            filename = f"browser_{int(time.time())}.png"
            path = str(LOGS_DIR / filename)
        page.screenshot(path=path)
        return {"success": True, "path": path, "message": f"Saved screenshot to {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def browser_wait_for(selector: str, timeout_ms: int = 10000) -> Dict[str, Any]:
    """Waits for an element to appear in the DOM."""
    try:
        page = get_browser_page()
        page.wait_for_selector(selector, timeout=timeout_ms)
        return {"success": True, "selector": selector, "message": f"Element '{selector}' appeared."}
    except Exception as e:
        return {"success": False, "selector": selector, "error": str(e)}
