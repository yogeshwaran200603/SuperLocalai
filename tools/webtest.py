"""
Astra-Local Web Testing Tools
Automates website UI testing, console error inspection, network failure detection,
broken image audits, interactive form verification, and screenshot reporting.
"""

import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from tools.browser import get_browser_page, browser_screenshot
from config import LOGS_DIR


def test_website(
    url: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    check_console: bool = True
) -> Dict[str, Any]:
    """
    Tests a website (e.g. http://localhost:3000):
    - Captures JavaScript console errors & warnings
    - Detects HTTP 4xx/5xx failed network requests
    - Checks for broken images (naturalWidth === 0)
    - Performs requested UI interaction actions (click, fill)
    - Captures screenshots of UI states and bugs
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url

    page = get_browser_page()

    console_errors = []
    console_warnings = []
    failed_requests = []

    def on_console(msg):
        if msg.type == "error":
            console_errors.append(msg.text)
        elif msg.type == "warning":
            console_warnings.append(msg.text)

    def on_request_failed(request):
        failed_requests.append({
            "url": request.url,
            "failure": request.failure,
            "method": request.method
        })

    def on_response(response):
        if response.status >= 400:
            failed_requests.append({
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text
            })

    # Attach listeners
    page.on("console", on_console)
    page.on("requestfailed", on_request_failed)
    page.on("response", on_response)

    bugs = []
    screenshots = []

    try:
        # 1. Navigate to target site
        response = page.goto(url, wait_until="networkidle", timeout=25000)
        http_status = response.status if response else 200

        if http_status >= 400:
            bugs.append(f"Server returned HTTP error status {http_status}")

        time.sleep(1)

        # 2. Check for broken images
        broken_imgs = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.filter(img => !img.complete || img.naturalWidth === 0).map(img => img.src);
        }""")
        if broken_imgs:
            for b in broken_imgs:
                bugs.append(f"Broken image source: {b}")

        # 3. Initial screenshot
        init_shot = str(LOGS_DIR / f"test_initial_{int(time.time())}.png")
        page.screenshot(path=init_shot, full_page=True)
        screenshots.append(init_shot)

        # 4. Perform interactive actions if specified
        if actions:
            for idx, act in enumerate(actions):
                act_type = act.get("action")
                selector = act.get("selector")
                try:
                    if act_type == "click":
                        page.click(selector, timeout=5000)
                    elif act_type in ("type", "fill"):
                        text = act.get("text", "")
                        page.fill(selector, text, timeout=5000)
                    time.sleep(0.5)
                except Exception as act_err:
                    bugs.append(f"Action '{act_type}' failed on '{selector}': {act_err}")
                    act_shot = str(LOGS_DIR / f"test_action_fail_{idx}_{int(time.time())}.png")
                    page.screenshot(path=act_shot)
                    screenshots.append(act_shot)

        # 5. Collect console errors as bugs
        for err in console_errors:
            bugs.append(f"JavaScript Console Error: {err}")

        # 6. Final screenshot
        final_shot = str(LOGS_DIR / f"test_final_{int(time.time())}.png")
        page.screenshot(path=final_shot)
        screenshots.append(final_shot)

        return {
            "success": True,
            "url": url,
            "page_title": page.title(),
            "http_status": http_status,
            "bugs_found": bugs,
            "bug_count": len(bugs),
            "console_errors": console_errors,
            "console_warnings": console_warnings,
            "failed_requests": failed_requests,
            "screenshots": screenshots,
            "summary": "No UI bugs or errors detected!" if len(bugs) == 0 else f"Found {len(bugs)} UI issues/bugs."
        }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e),
            "bugs_found": bugs,
            "screenshots": screenshots
        }
    finally:
        # Remove listeners to prevent duplicate triggers on next tests
        try:
            page.remove_listener("console", on_console)
            page.remove_listener("requestfailed", on_request_failed)
            page.remove_listener("response", on_response)
        except Exception:
            pass
