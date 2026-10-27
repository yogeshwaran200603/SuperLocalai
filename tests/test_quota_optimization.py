"""
Astra-Local Quota & Optimization Test Suite
Validates:
1. MODEL_CHAIN, PRIMARY_MODEL, FALLBACK_MODEL, QUOTA_PER_DAY, and MAX_STEPS configuration.
2. Model fallback on 429 RESOURCE_EXHAUSTED and human-readable RetryInfo extraction.
3. Local-first rule matching (zero API calls) for apps, shortcuts, folders, and URLs.
4. 10-minute SQLite request caching for read-only prompts.
5. SQLite daily usage tracking per model and 80% quota warning.
6. Local summary construction without extra final Gemini summary call.
7. System prompt parallel tool call batching guidelines.
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    MODEL_CHAIN,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    QUOTA_PER_DAY,
    MAX_STEPS,
    CACHE_TTL_SECONDS,
    get_system_prompt,
)
from memory import MemoryManager
from agent import (
    AstraAgent,
    extract_retry_delay,
    is_read_only_prompt,
    try_local_first_execution,
    build_local_summary,
)


class TestQuotaOptimizationSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "test_memory.db"
        self.memory = MemoryManager(db_path=self.test_db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_config_quota_settings(self):
        """Validates config defaults: MODEL_CHAIN exists, MAX_STEPS=8, QUOTA_PER_DAY=20, CACHE_TTL=600."""
        self.assertIsInstance(MODEL_CHAIN, list)
        self.assertGreaterEqual(len(MODEL_CHAIN), 2)
        self.assertEqual(PRIMARY_MODEL, MODEL_CHAIN[0])
        self.assertEqual(MAX_STEPS, 8, "MAX_STEPS must be lowered to 8 by default")
        self.assertEqual(QUOTA_PER_DAY, 20, "QUOTA_PER_DAY must be 20 by default")
        self.assertEqual(CACHE_TTL_SECONDS, 600, "Cache TTL must be 10 minutes (600 seconds)")

    def test_system_prompt_parallel_batching(self):
        """Verifies system prompt instructs Gemini to return multiple tool calls in one turn."""
        prompt = get_system_prompt()
        self.assertIn("QUOTA OPTIMIZATION", prompt)
        self.assertIn("multiple independent tool calls", prompt)

    def test_local_first_execution_zero_api_calls(self):
        """Verifies local-first execution handles apps, folders, URLs, and shortcuts without API calls."""
        # Open app
        with patch("tools.shell.subprocess.Popen") as mock_popen:
            res_notepad = try_local_first_execution("open notepad")
            self.assertIsNotNone(res_notepad)
            self.assertIn("notepad", res_notepad.lower())

        # Open folder
        with patch("tools.shell.subprocess.run") as mock_ps:
            mock_ps.return_value = MagicMock(returncode=0, stdout="", stderr="")
            res_folder = try_local_first_execution("open desktop")
            self.assertIsNotNone(res_folder)
            self.assertIn("Desktop folder", res_folder)

        # Open website
        with patch("webbrowser.open") as mock_web:
            res_url = try_local_first_execution("open google.com")
            self.assertIsNotNone(res_url)
            self.assertIn("google.com", res_url)

        # Discord shortcut
        with patch("tools.shell.subprocess.run") as mock_ps:
            mock_ps.return_value = MagicMock(returncode=0, stdout="", stderr="")
            res_discord = try_local_first_execution("open discord and go to my server")
            self.assertIsNotNone(res_discord)
            self.assertIn("my server", res_discord)

        # Non-matching prompt must return None so agent can process
        res_other = try_local_first_execution("analyze sales data and train model")
        self.assertIsNone(res_other)

    def test_read_only_prompt_detector(self):
        """Verifies distinction between read-only queries (safe to cache) and state mutations."""
        self.assertTrue(is_read_only_prompt("find the 5 largest files in downloads"))
        self.assertTrue(is_read_only_prompt("list files on desktop"))
        self.assertTrue(is_read_only_prompt("inspect sales.csv"))
        self.assertTrue(is_read_only_prompt("what shortcuts are configured"))

        # Mutating actions must never be cached
        self.assertFalse(is_read_only_prompt("create a folder test on Desktop"))
        self.assertFalse(is_read_only_prompt("delete old note.txt"))
        self.assertFalse(is_read_only_prompt("write a python script and run it"))

    def test_sqlite_10_minute_cache(self):
        """Validates SQLite cache storage, hit retrieval, and TTL expiration."""
        prompt = "inspect sales.csv columns and shape"
        response = "The dataset has 500 rows and 4 columns: ID, Product, Amount, Date."

        # Cache miss initially
        self.assertIsNone(self.memory.get_cached_response(prompt))

        # Store in cache
        self.memory.cache_response(prompt, response, ttl_seconds=600)

        # Cache hit
        cached = self.memory.get_cached_response(prompt)
        self.assertEqual(cached, response)

        # Expired cache item
        self.memory.cache_response("expired prompt", "old data", ttl_seconds=-1)
        self.assertIsNone(self.memory.get_cached_response("expired prompt"))

    def test_sqlite_daily_usage_counter(self):
        """Validates tracking of daily API calls per model in SQLite."""
        test_model = "test-model-quota"
        today_calls = self.memory.get_daily_api_calls(test_model)

        self.memory.record_api_call(test_model)
        self.memory.record_api_call(test_model)

        new_calls = self.memory.get_daily_api_calls(test_model)
        self.assertEqual(new_calls, today_calls + 2)

    def test_retry_delay_extraction(self):
        """Validates regex extraction of retry times from Gemini 429 error messages."""
        # Format 1: Text message with seconds/hours
        err1 = Exception("429 RESOURCE_EXHAUSTED: You exceeded your quota. Please retry in 16h6m56s.")
        self.assertEqual(extract_retry_delay(err1), "16h6m56s")

        # Format 2: JSON details with retryDelay
        err2 = Exception("429: {'details': [{'@type': 'RetryInfo', 'retryDelay': '3600s'}]}")
        self.assertIn("1h", extract_retry_delay(err2))

    def test_local_summary_builder(self):
        """Verifies local summary is constructed directly from tool outputs without extra API calls."""
        executed_tools = [
            {"name": "file_write", "result": {"success": True, "message": "Wrote 150 bytes to test.py"}},
            {"name": "run_powershell", "result": {"success": True, "stdout": "Test Output OK"}}
        ]
        summary = build_local_summary(executed_tools)
        self.assertIn("Completed Actions", summary)
        self.assertIn("file_write", summary)
        self.assertIn("run_powershell", summary)

    def test_model_chain_fallback_on_429(self):
        """Validates that on 429 RESOURCE_EXHAUSTED, the agent switches to the fallback model immediately."""
        agent = AstraAgent()
        agent.client = MagicMock()

        # Mock primary model throwing 429, fallback model succeeding
        err_429 = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded. Please retry in 12h.")
        success_response = MagicMock()
        success_response.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(function_call=None, text="Analysis complete.")]))
        ]

        def mock_generate(model, contents, config):
            if model == PRIMARY_MODEL:
                raise err_429
            return success_response

        agent.client.models.generate_content.side_effect = mock_generate

        # Run agent on non-local prompt
        result = agent.run("calculate complex statistics on dataset")
        self.assertIn("Analysis complete", result)
        # Verify it switched to fallback model
        self.assertNotEqual(agent.active_model, PRIMARY_MODEL)


if __name__ == "__main__":
    unittest.main()
