"""
Astra-Local Tools Package Registry
Exports all tools and provides a unified mapping for Gemini function calling.
"""

from tools.shell import run_powershell, open_url, open_app
from tools.browser import (
    browser_goto,
    browser_click,
    browser_type,
    browser_press,
    browser_read_text,
    browser_screenshot,
    browser_wait_for,
    close_browser,
)
from tools.whatsapp import whatsapp_send
from tools.desktop import (
    desktop_screenshot,
    desktop_click,
    desktop_type,
    desktop_hotkey,
    desktop_focus_window,
    desktop_locate_element,
    discord_goto,
    get_screen_text,
)
from tools.files import (
    file_read,
    file_write,
    file_list,
    file_move,
    file_delete,
)
from tools.python_exec import run_python
from tools.data import (
    data_inspect,
    data_clean,
    data_chart,
    data_train_model,
)
from tools.docs import (
    doc_create_pptx,
    doc_create_docx,
    doc_create_xlsx,
    doc_create_pdf,
)
from tools.devtools import (
    scaffold_project,
    run_tests,
    fix_and_rerun,
)
from tools.webtest import test_website
from tools.chess_tools import (
    chess_benchmark,
    chess_analyze_pgn,
    chess_play_bot,
)

# Tool registry for dynamic execution by name
TOOL_REGISTRY = {
    # Shell & OS
    "run_powershell": run_powershell,
    "open_url": open_url,
    "open_app": open_app,
    # Browser
    "browser_goto": browser_goto,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_press": browser_press,
    "browser_read_text": browser_read_text,
    "browser_screenshot": browser_screenshot,
    "browser_wait_for": browser_wait_for,
    # WhatsApp
    "whatsapp_send": whatsapp_send,
    # Desktop
    "desktop_screenshot": desktop_screenshot,
    "desktop_click": desktop_click,
    "desktop_type": desktop_type,
    "desktop_hotkey": desktop_hotkey,
    "desktop_focus_window": desktop_focus_window,
    "desktop_locate_element": desktop_locate_element,
    "discord_goto": discord_goto,
    "get_screen_text": get_screen_text,
    # Files
    "file_read": file_read,
    "file_write": file_write,
    "file_list": file_list,
    "file_move": file_move,
    "file_delete": file_delete,
    # Python
    "run_python": run_python,
    # Data
    "data_inspect": data_inspect,
    "data_clean": data_clean,
    "data_chart": data_chart,
    "data_train_model": data_train_model,
    # Docs
    "doc_create_pptx": doc_create_pptx,
    "doc_create_docx": doc_create_docx,
    "doc_create_xlsx": doc_create_xlsx,
    "doc_create_pdf": doc_create_pdf,
    # Dev
    "scaffold_project": scaffold_project,
    "run_tests": run_tests,
    "fix_and_rerun": fix_and_rerun,
    # Web Testing
    "test_website": test_website,
    # Chess
    "chess_benchmark": chess_benchmark,
    "chess_analyze_pgn": chess_analyze_pgn,
    "chess_play_bot": chess_play_bot,
}
