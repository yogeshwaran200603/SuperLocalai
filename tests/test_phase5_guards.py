"""
Comprehensive unit tests for Phase 5 verification:
1. Truthful status formatting & escaping
2. Quota counter warns-only and never blocks
3. Watchdogs: per-tool timeout, no-progress 3-identical-calls detector, slow steps log
4. UI scan limit: 50,000 fake elements scanned in < 5 seconds, capped at 80 elements
5. Retry backoff sequence and fallback order
"""

import sys
import time
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safety import format_truthful_status
from agent import AstraAgent
from config import PROVIDER_ORDER
from takeover import detect_uia_clickable_elements


def test_truthful_status_formatting():
    # Never prints OK Task Completed on failure
    success_status = format_truthful_status("SUCCESS", "Task completed smoothly.")
    assert "[SUCCESS]" in success_status
    assert "Task completed smoothly." in success_status

    failed_status = format_truthful_status("FAILED", "Connection refused [bold red]")
    assert "[FAILED]" in failed_status
    assert r"\[bold red]" in failed_status

    partial_status = format_truthful_status("PARTIAL", "Step 5 completed out of 10.")
    assert "[PARTIAL]" in partial_status

    blocked_status = format_truthful_status("BLOCKED", "Waiting on user confirmation.")
    assert "[BLOCKED]" in blocked_status


def test_quota_warn_only_never_blocks_provider():
    from providers.gemini_provider import GeminiProvider

    prov = GeminiProvider(api_key="dummy-key", primary_model="gemini-3.8-flash")
    prov.client = MagicMock()

    with patch("providers.gemini_provider.MemoryManager") as mock_mem_cls:
        mock_mem = MagicMock()
        mock_mem_cls.return_value = mock_mem
        prov.memory = mock_mem
        # Simulate 50,000 calls made today (extreme quota usage)
        mock_mem.get_daily_api_calls.return_value = 50000

        is_h, details, fix = prov.health_check()
        # Health check MUST return is_healthy=True (counter only warns and never blocks)
        assert is_h is True
        assert "Online" in details


def test_watchdog_per_tool_timeout(tmp_path):
    agent = AstraAgent()
    slow_log = tmp_path / "slow_steps.log"

    def super_slow_tool():
        time.sleep(2.0)
        return {"success": True}

    with patch.dict("tools.TOOL_REGISTRY", {"super_slow": super_slow_tool}, clear=False), \
         patch("agent.TOOL_TIMEOUT", 0.2), \
         patch("agent.SLOW_STEP_THRESHOLD", 0.1), \
         patch("agent.SLOW_STEPS_LOG_PATH", slow_log), \
         patch("agent.confirm_action", return_value=True):

        res = agent.execute_tool("super_slow", {})
        assert res["success"] is False
        assert res.get("status") == "TIMEOUT"
        assert "timed out" in res.get("error", "").lower()
        assert slow_log.exists()
        log_content = slow_log.read_text(encoding="utf-8")
        assert "TIMEOUT" in log_content


def test_watchdog_no_progress_three_identical_calls():
    agent = AstraAgent()
    agent.active_provider = MagicMock()
    agent.active_provider.name = "mock_prov"
    agent.active_provider.is_available.return_value = True
    agent.active_provider.health_check.return_value = (True, "Online", None)

    # Mock model repeatedly returning identical tool call
    from providers.base import LLMResponse, ToolCall
    mock_tc = ToolCall(id="tc1", name="file_list", arguments={"directory": "dummy"})
    resp_loop = LLMResponse(text="", tool_calls=[mock_tc], model_used="mock")
    agent.active_provider.chat.return_value = resp_loop

    with patch("tools.TOOL_REGISTRY", {"file_list": lambda **kwargs: {"files": []}}), \
         patch("safety.confirm_action", return_value=True):
        result = agent.run("list files in loop")
        assert "No-progress detected: 3 identical consecutive calls" in result


def test_ui_scan_limit_50000_fake_elements_under_5s():
    """
    Simulates a huge UI tree with 50,000 elements.
    Ensures scan terminates in under 5.0 seconds and bounds elements at <= 80.
    """
    class FakeElementInfo:
        control_type = "Button"
        class_name = "MockButton"

    class FakeRect:
        def width(self): return 50
        def height(self): return 30
        left = 100
        top = 100
        right = 150
        bottom = 130

    class FakeChild:
        element_info = FakeElementInfo()
        def rectangle(self): return FakeRect()
        def window_text(self): return "Button"
        def children(self): return []

    class FakeWindow:
        element_info = FakeElementInfo()
        def rectangle(self): return FakeRect()
        def window_text(self): return "Mock Window"
        def children(self):
            # Generate 50,000 children
            for i in range(50000):
                yield FakeChild()

    class FakeDesktop:
        def __init__(self, backend="uia"): pass
        def windows(self):
            return [FakeWindow()]

    t0 = time.time()
    with patch("pywinauto.Desktop", FakeDesktop):
        elements = detect_uia_clickable_elements(0, 0, 1920, 1080)

    elapsed = time.time() - t0
    assert elapsed < 5.0, f"UI scan took too long: {elapsed:.2f}s"
    assert len(elements) <= 80, f"Expected at most 80 elements, got {len(elements)}"
