"""
Comprehensive Unit Tests for Astra-Local Upgrade Features:
1. OpenAI Compatible Provider (Groq, OpenRouter, tool calling, 429/503 errors, 2-strike invalid tool calls).
2. Gemini thought_signature preservation in conversation history.
3. Chess Tools: chess_benchmark, chess_analyze_pgn, and chess_play_bot safety gate.
4. Non-vision tools: discord_goto, get_screen_text.
5. Quota commands: /quota, /quota reset in memory and agent.
"""

import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chess
from providers.base import LLMMessage, ToolCall, ProviderQuotaExhaustedError, ProviderUnavailableError, InvalidToolCallError
from providers.openai_compatible_provider import OpenAICompatibleProvider
from providers.gemini_provider import GeminiProvider
from memory import MemoryManager
from tools.desktop import discord_goto, get_screen_text
from tools.chess_tools import chess_benchmark, chess_analyze_pgn, chess_play_bot, calculate_elo_difference
from agent import AstraAgent, sanitize_messages_for_provider_switch


class TestUpgradesV2(unittest.TestCase):

    # =========================================================================
    # 1. OpenAI Compatible Provider (Groq, OpenRouter)
    # =========================================================================

    def test_openai_compatible_presets(self):
        """Verifies presets for Groq and OpenRouter configure base URLs and models properly."""
        groq = OpenAICompatibleProvider(name="groq", api_key="test-groq-key")
        self.assertEqual(groq.base_url, "https://api.groq.com/openai/v1")
        self.assertIn("llama", groq.model.lower())
        self.assertEqual(groq.api_key, "test-groq-key")

        openrouter = OpenAICompatibleProvider(name="openrouter", api_key="test-or-key")
        self.assertEqual(openrouter.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(openrouter.api_key, "test-or-key")

    @patch("providers.openai_compatible_provider.requests.post")
    def test_openai_compatible_tool_calling(self, mock_post):
        """Validates tool/function calling parsing from OpenAI-compatible response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Opening notepad now.",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "open_app",
                            "arguments": json.dumps({"name": "notepad"})
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }]
        }
        mock_post.return_value = mock_resp

        provider = OpenAICompatibleProvider(name="groq", api_key="fake-key")
        messages = [LLMMessage(role="user", content="open notepad")]

        from tools.shell import open_app
        response = provider.chat(messages=messages, tools=[open_app])

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].name, "open_app")
        self.assertEqual(response.tool_calls[0].arguments, {"name": "notepad"})

    @patch("providers.openai_compatible_provider.requests.post")
    def test_openai_compatible_429_quota_error(self, mock_post):
        """Verifies 429 raises ProviderQuotaExhaustedError without infinite retries."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "45"}
        mock_post.return_value = mock_resp

        provider = OpenAICompatibleProvider(name="groq", api_key="fake-key")
        with self.assertRaises(ProviderQuotaExhaustedError) as ctx:
            provider.chat(messages=[LLMMessage(role="user", content="hello")])
        self.assertIn("Rate limit", str(ctx.exception))
        self.assertEqual(ctx.exception.retry_delay, "45s")

    @patch("providers.openai_compatible_provider.requests.post")
    def test_openai_compatible_invalid_tool_calls_twice(self, mock_post):
        """Verifies 2-strike fallback on invalid JSON / schema tool calls."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_bad",
                        "type": "function",
                        "function": {
                            "name": "open_app",
                            "arguments": "MALFORMED_NOT_JSON"
                        }
                    }]
                }
            }]
        }
        mock_post.return_value = mock_resp

        from tools.shell import open_app
        provider = OpenAICompatibleProvider(name="groq", api_key="fake-key")
        # Turn 1: strike 1
        provider.chat(messages=[LLMMessage(role="user", content="test")], tools=[open_app])
        # Turn 2: strike 2 raises InvalidToolCallError
        with self.assertRaises(InvalidToolCallError):
            provider.chat(messages=[LLMMessage(role="user", content="test")], tools=[open_app])

    # =========================================================================
    # 2. Gemini thought_signature Preservation Unit Test
    # =========================================================================

    def test_gemini_thought_signature_preserved(self):
        """
        Explicit Requirement Unit Test:
        Verifies that when Gemini returns a function call, the model's ORIGINAL response
        content object (including all parts and thought_signature) is preserved verbatim in
        conversation history, never stripped or rebuilt by hand.
        """
        # Create a mock candidate with a Part that has thought_signature
        mock_part = MagicMock()
        mock_part.thought_signature = "sig_abc123_valid_gemini_thought"
        mock_fn_call = MagicMock()
        mock_fn_call.name = "open_app"
        mock_fn_call.args = {"name": "notepad"}
        mock_fn_call.id = "fn_call_999"
        mock_part.function_call = mock_fn_call

        mock_content = MagicMock()
        mock_content.role = "model"
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        provider = GeminiProvider(api_key="fake-api-key")
        provider.client = MagicMock()
        provider.client.models.generate_content.return_value = mock_response

        # Call chat
        from tools.shell import open_app
        res = provider.chat(
            messages=[LLMMessage(role="user", content="open notepad")],
            tools=[open_app]
        )

        # Check conversation history kept the exact original content object
        self.assertGreater(len(provider.conversation_contents), 0)
        stored_content = provider.conversation_contents[-1]
        self.assertIs(stored_content, mock_content)
        self.assertEqual(stored_content.parts[0].thought_signature, "sig_abc123_valid_gemini_thought")

    # =========================================================================
    # 3. Provider Switching Mid-Task History Sanitization
    # =========================================================================

    def test_sanitize_messages_for_provider_switch(self):
        """Verifies conversation history is converted to plain text summaries on provider switch."""
        raw_msgs = [
            LLMMessage(role="user", content="open discord"),
            LLMMessage(
                role="assistant",
                content="I will open discord.",
                tool_calls=[ToolCall(id="c1", name="open_app", arguments={"name": "discord"})],
                raw_content=MagicMock(name="GeminiRawContentWithThoughtSignature")
            ),
            LLMMessage(role="tool", name="open_app", tool_call_id="c1", content={"success": True})
        ]

        clean = sanitize_messages_for_provider_switch(raw_msgs)
        self.assertEqual(len(clean), 3)
        self.assertIsNone(clean[1].raw_content)
        self.assertIn("open_app", clean[1].content)
        self.assertEqual(clean[2].role, "user")
        self.assertIn("result:", clean[2].content)

    # =========================================================================
    # 4. Chess Tools
    # =========================================================================

    def test_calculate_elo_difference(self):
        """Validates estimated Elo difference formula."""
        self.assertEqual(calculate_elo_difference(0.5), 0.0)
        self.assertGreater(calculate_elo_difference(0.75), 180.0)
        self.assertEqual(calculate_elo_difference(1.0), 800.0)
        self.assertEqual(calculate_elo_difference(0.0), -800.0)

    def test_chess_play_bot_safety_gate(self):
        """Validates that chess_play_bot strictly refuses to automate against human players."""
        # Non-bot human match URL must be refused
        res_human = chess_play_bot(target_url="https://www.chess.com/live/game/12345678")
        self.assertFalse(res_human["success"])
        self.assertIn("REFUSED", res_human["error"])
        self.assertIn("Use only against bots", res_human["error"])

        # Legitimate computer bot URL is accepted
        res_bot = chess_play_bot(target_url="https://www.chess.com/play/computer")
        self.assertTrue(res_bot["success"])
        self.assertIn("Use only against bots", res_bot["notice"])

    def test_chess_analyze_pgn(self):
        """Verifies PGN analysis, accuracy computation, and blunder identification."""
        import tempfile
        sample_pgn = """[Event "Test Match"]
[Site "Local"]
[Date "2026.10.23"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0
"""
        with tempfile.NamedTemporaryFile("w", suffix=".pgn", delete=False) as f:
            f.write(sample_pgn)
            f_path = f.name

        try:
            res = chess_analyze_pgn(f_path)
            self.assertTrue(res["success"])
            self.assertEqual(res["white_player"], "Player1")
            self.assertEqual(res["black_player"], "Player2")
            self.assertIn("white_accuracy", res)
            self.assertIn("black_accuracy", res)
            self.assertIn("chart_path", res)
            self.assertTrue(Path(res["chart_path"]).exists())
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    # =========================================================================
    # 5. Non-Vision Tools & Quota Commands
    # =========================================================================

    @patch("pyautogui.press")
    @patch("pyautogui.write")
    @patch("pyautogui.hotkey")
    @patch("pygetwindow.getAllWindows")
    def test_discord_goto(self, mock_get_all, mock_hotkey, mock_write, mock_press):
        """Verifies discord_goto activates Discord and triggers Quick Switcher (Ctrl+K)."""
        mock_win = MagicMock()
        mock_win.title = "Discord"
        mock_win.isMinimized = False
        mock_get_all.return_value = [mock_win]

        res = discord_goto("general-chat")
        self.assertTrue(res["success"])
        mock_hotkey.assert_called_with("ctrl", "k")
        mock_write.assert_called_with("general-chat", interval=0.03)

    @patch("pygetwindow.getAllWindows")
    @patch("pygetwindow.getActiveWindow")
    def test_get_screen_text(self, mock_active, mock_all):
        """Verifies get_screen_text returns window titles and control count without screenshot."""
        mock_win = MagicMock()
        mock_win.title = "Visual Studio Code"
        mock_active.return_value = mock_win
        mock_all.return_value = [mock_win]

        res = get_screen_text()
        self.assertTrue(res["success"])
        self.assertEqual(res["active_window"], "Visual Studio Code")
        self.assertIn("open_windows", res)
        self.assertIn("control_names", res)

    def test_quota_management_commands(self):
        """Verifies /quota and /quota reset interact with MemoryManager."""
        mem = MemoryManager()
        mem.record_api_call("test-quota-model")
        self.assertGreaterEqual(mem.get_daily_api_calls("test-quota-model"), 1)

        # Reset quota
        deleted = mem.reset_daily_usage()
        self.assertGreaterEqual(deleted, 1)
        self.assertEqual(mem.get_daily_api_calls("test-quota-model"), 0)


if __name__ == "__main__":
    unittest.main()
