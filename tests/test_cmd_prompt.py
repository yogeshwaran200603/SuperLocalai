"""
Unit tests for Command Prompt (CMD) argument handling, app aliases, and UTF-8 compatibility.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

from agent import try_local_first_execution
from tools.shell import open_app
from providers.gemini_provider import GeminiProvider


class TestCmdPromptCompatibility(unittest.TestCase):

    def test_cmd_prompt_local_first(self):
        """Verifies that 'open cmd prompt', 'cmd prompt', 'command prompt', and 'terminal' run locally."""
        with patch("agent.open_app") as mock_open:
            mock_open.return_value = {"success": True}

            # 1. 'open cmd prompt'
            res = try_local_first_execution("open cmd prompt")
            self.assertIsNotNone(res)
            self.assertIn("cmd prompt", res)
            mock_open.assert_called_with("cmd")

            # 2. 'cmd prompt' direct without 'open'
            res = try_local_first_execution("cmd prompt")
            self.assertIsNotNone(res)
            mock_open.assert_called_with("cmd")

            # 3. 'command prompt'
            res = try_local_first_execution("command prompt")
            self.assertIsNotNone(res)
            mock_open.assert_called_with("cmd")

            # 4. 'terminal'
            res = try_local_first_execution("terminal")
            self.assertIsNotNone(res)
            mock_open.assert_called_with("cmd")

    def test_cmd_argument_escaping(self):
        """Verifies that Windows CMD quote escapes like '\\ open notepad\\' are cleaned correctly."""
        with patch("agent.open_app") as mock_open:
            mock_open.return_value = {"success": True}

            # CMD escaped input: \ open notepad\
            res = try_local_first_execution(r"\ open notepad\\")
            self.assertIsNotNone(res)
            self.assertIn("notepad", res)

            # CMD unclosed quote with leading space: " open notepad
            res = try_local_first_execution('" open notepad')
            self.assertIsNotNone(res)
            self.assertIn("notepad", res)

    def test_open_app_cmd_aliases(self):
        """Verifies that tools.shell.open_app normalizes cmd prompt aliases."""
        with patch("tools.shell.run_powershell") as mock_ps:
            mock_ps.return_value = {"success": True, "stdout": "", "stderr": "", "exit_code": 0}

            open_app("cmd prompt")
            mock_ps.assert_called_with('Start-Process "cmd"')

            open_app("command prompt")
            mock_ps.assert_called_with('Start-Process "cmd"')

    def test_gemini_health_check_model_chain_fallback(self):
        """Verifies that if primary model has reached quota, health_check falls back to next model in chain."""
        with patch("providers.gemini_provider.MemoryManager") as mock_mem_cls:
            mock_mem = MagicMock()
            mock_mem_cls.return_value = mock_mem

            # Primary model exhausted (20 calls), fallback model has 0 calls
            def get_calls(model_name):
                if model_name == "gemini-3-flash-preview":
                    return 20
                return 0

            mock_mem.get_daily_api_calls.side_effect = get_calls

            prov = GeminiProvider(
                api_key="fake-key",
                model_chain=["gemini-3-flash-preview", "gemini-3.5-flash-lite"],
                primary_model="gemini-3-flash-preview"
            )
            prov.client = MagicMock()

            is_h, details, fix = prov.health_check()
            self.assertTrue(is_h)
            self.assertIn("gemini-3.5-flash-lite", details)


if __name__ == "__main__":
    unittest.main()
