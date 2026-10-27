"""
Astra-Local WhatsApp Web Automation Module
Dedicated selectors for WhatsApp Web, persistent QR session, Gemini Vision fallback,
and mandatory confirmation before pressing Send.
"""

import time
import base64
from typing import Dict, Any, Optional
from rich.console import Console
from rich.prompt import Confirm

from tools.browser import get_browser_page, browser_screenshot
from safety import log_action
from config import GEMINI_API_KEY, MODEL_NAME

console = Console()

# Primary selectors for WhatsApp Web UI
SEARCH_SELECTORS = [
    'div[contenteditable="true"][data-tab="3"]',
    'div[title="Search input textbox"]',
    '[aria-label="Search input textbox"]',
    'div[data-testid="chat-list-search"]',
    'div._ai04',
]

FIRST_RESULT_SELECTORS = [
    'div[role="listitem"]',
    'div[data-testid="cell-frame-container"]',
    'div._ak72',
    'div._ak8l',
]

MESSAGE_BOX_SELECTORS = [
    'footer div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"]',
    'div[title="Type a message"]',
    'div[data-testid="conversation-compose-box-input"]',
]

SEND_BUTTON_SELECTORS = [
    'button[data-testid="compose-btn-send"]',
    'span[data-icon="send"]',
    'button[aria-label="Send"]',
]


def _find_element(page, selectors: list):
    """Tries a list of selectors in order and returns the first matching locator."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                return loc, sel
        except Exception:
            continue
    return None, None


def _vision_locate_element(image_path: str, element_description: str) -> Optional[tuple]:
    """
    Fallback: Uses Gemini Vision to analyze a screenshot and estimate coordinates (x, y)
    of a requested UI element if selectors fail.
    """
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        prompt = (
            f"You are analyzing a 1280x800 WhatsApp Web screenshot. "
            f"Locate the {element_description}. Return ONLY two numbers separated by a comma: X,Y "
            f"representing the pixel coordinates inside the element. Example: 450,220"
        )
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
        console.print(f"[yellow]Vision fallback notice: {e}[/yellow]")
    return None


def whatsapp_send(contact: str, message: str) -> Dict[str, Any]:
    """
    Automates sending a WhatsApp message via WhatsApp Web using persistent Playwright Chromium.
    1. Opens https://web.whatsapp.com.
    2. Searches for contact.
    3. Opens conversation.
    4. Types message.
    5. Prompts user for mandatory confirmation: Send '<message>' to '<contact>'? (y/n)
    6. Sends if approved.
    """
    try:
        page = get_browser_page()
        console.print(f"[cyan]Navigating to WhatsApp Web...[/cyan]")
        page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)

        # Allow time for QR scan or chat load
        console.print("[dim]Waiting for WhatsApp interface to load (scan QR if first time)...[/dim]")
        time.sleep(4)

        # 1. Locate Search Box
        search_box, _ = _find_element(page, SEARCH_SELECTORS)
        if not search_box:
            # Fallback to screenshot + vision
            shot = browser_screenshot()
            coords = _vision_locate_element(shot["path"], "search or start new chat input box")
            if coords:
                page.mouse.click(coords[0], coords[1])
            else:
                return {
                    "success": False,
                    "error": "Could not find WhatsApp search box. Please ensure WhatsApp Web is logged in.",
                    "screenshot": shot.get("path")
                }
        else:
            search_box.click()

        time.sleep(0.5)
        page.keyboard.type(contact, delay=50)
        time.sleep(2)

        # 2. Select first search result
        first_result, _ = _find_element(page, FIRST_RESULT_SELECTORS)
        if first_result:
            first_result.click()
        else:
            # Press enter to open top match
            page.keyboard.press("Enter")
        time.sleep(1.5)

        # 3. Locate message box
        msg_box, _ = _find_element(page, MESSAGE_BOX_SELECTORS)
        if not msg_box:
            shot = browser_screenshot()
            coords = _vision_locate_element(shot["path"], "type a message input area at the bottom")
            if coords:
                page.mouse.click(coords[0], coords[1])
            else:
                return {
                    "success": False,
                    "error": f"Opened chat for '{contact}' but could not locate message input box.",
                    "screenshot": shot.get("path")
                }
        else:
            msg_box.click()

        time.sleep(0.5)
        page.keyboard.type(message, delay=25)
        time.sleep(0.5)

        # 4. Mandatory User Confirmation
        console.print(f"\n[bold magenta]PRE-SEND VERIFICATION[/bold magenta]")
        console.print(f"Target Contact: [bold green]{contact}[/bold green]")
        console.print(f"Message Content: [bold yellow]\"{message}\"[/bold yellow]\n")

        confirmed = Confirm.ask(f"[bold]Send '{message}' to '{contact}'? (y/n)[/bold]", default=False)
        log_action("whatsapp_send", {"contact": contact, "message": message}, "CONFIRMED" if confirmed else "CANCELLED")

        if not confirmed:
            return {
                "success": False,
                "message": f"Send cancelled by user. Message '{message}' was typed into chat with '{contact}' but NOT sent.",
                "status": "USER_ABORTED"
            }

        # 5. Send message
        send_btn, _ = _find_element(page, SEND_BUTTON_SELECTORS)
        if send_btn:
            send_btn.click()
        else:
            page.keyboard.press("Enter")

        time.sleep(1)
        return {
            "success": True,
            "contact": contact,
            "message": message,
            "status": "SENT"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"WhatsApp automation error: {str(e)}"
        }
