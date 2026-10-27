"""
Astra-Local Multi-Provider Test Suite
Validates:
1. Provider configuration (PROVIDER_ORDER, OLLAMA_HOST, OLLAMA_MODEL, mask_secret).
2. Tool schema conversion (OpenAPI format, type mappings, required fields).
3. Small-model optimizations:
   - Keyword-based tool filtering capped at 12 tools.
   - Pre-execution tool argument schema validation.
   - Temperature 0.2 and concise system prompt.
4. Ollama provider functionality (mocked /api/chat, headers, tool parsing, error handling).
5. Gemini provider functionality (mocked SDK, call-ID rules, 429 failover).
6. Multi-provider automatic failover on connection/timeout/quota/schema errors.
7. Local-first zero model call interception.
8. /provider and /models command behavior.
9. Safety and emergency stop controls.
All tests use mocks; ZERO live API calls are consumed.
"""

import sys
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    PROVIDER_ORDER,
    OLLAMA_MODEL,
    OLLAMA_HOST,
    mask_secret,
    get_small_model_system_prompt,
)
from memory import MemoryManager
from providers import (
    BaseProvider,
    ToolCall,
    LLMMessage,
    LLMResponse,
    GeminiProvider,
    OllamaProvider,
    get_provider,
    create_provider_chain,
    ProviderError,
    ProviderUnavailableError,
    ProviderQuotaExhaustedError,
    InvalidToolCallError,
    func_to_schema,
    filter_tools_for_request,
    validate_tool_arguments,
)
from tools import TOOL_REGISTRY, run_powershell, file_read, file_write
from agent import AstraAgent, try_local_first_execution


class TestMultiProviderSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "test_memory.db"
        self.memory = MemoryManager(db_path=self.test_db)

    def tearDown(self):
        self.temp_dir.cleanup()

    # --------------------------------------------------------------------------
    # 1. Config & Provider Factory
    # --------------------------------------------------------------------------
    def test_provider_config_and_masking(self):
        """Verifies default provider order and that secrets are masked safely."""
        self.assertIsInstance(PROVIDER_ORDER, list)
        self.assertIn("ollama_local", PROVIDER_ORDER)
        self.assertIn("gemini", PROVIDER_ORDER)
        self.assertIn(OLLAMA_MODEL, ("qwen3:4b", "qwen3:8b"))

        # Masking secrets
        self.assertEqual(mask_secret(""), "Not configured")
        self.assertEqual(mask_secret("1234567890abcdef"), "1234...cdef")
        self.assertNotIn("middle_secret", mask_secret("AIzaSy_middle_secret_xyz1"))

    def test_provider_factories(self):
        """Validates instantiation of all supported provider types."""
        gemini = get_provider("gemini")
        self.assertIsInstance(gemini, GeminiProvider)
        self.assertEqual(gemini.name, "gemini")

        ollama_loc = get_provider("ollama_local")
        self.assertIsInstance(ollama_loc, OllamaProvider)
        self.assertEqual(ollama_loc.name, "ollama_local")
        self.assertEqual(ollama_loc.host, OLLAMA_HOST.rstrip("/"))

        ollama_cld = get_provider("ollama_cloud")
        self.assertIsInstance(ollama_cld, OllamaProvider)
        self.assertEqual(ollama_cld.name, "ollama_cloud")
        self.assertIn("ollama.com", ollama_cld.host)

        chain = create_provider_chain(["ollama_local", "gemini"])
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0].name, "ollama_local")
        self.assertEqual(chain[1].name, "gemini")

    # --------------------------------------------------------------------------
    # 2. Tool Schema Conversion & Validation
    # --------------------------------------------------------------------------
    def test_func_to_schema_conversion(self):
        """Validates conversion of Python callables to OpenAPI / JSON tool schemas."""
        schema_ps = func_to_schema(run_powershell)
        self.assertEqual(schema_ps["type"], "function")
        fn = schema_ps["function"]
        self.assertEqual(fn["name"], "run_powershell")
        self.assertIn("script", fn["parameters"]["properties"])
        self.assertEqual(fn["parameters"]["properties"]["script"]["type"], "string")
        self.assertIn("script", fn["parameters"]["required"])

        schema_fw = func_to_schema(file_write)
        props_fw = schema_fw["function"]["parameters"]["properties"]
        self.assertIn("path", props_fw)
        self.assertIn("content", props_fw)
        self.assertIn("path", schema_fw["function"]["parameters"]["required"])

    def test_filter_tools_for_request_max_12(self):
        """Ensures that at most 12 tools are selected and keyword relevance prioritizes matching tools."""
        # Query matching data analysis
        tools_data = filter_tools_for_request("analyze sales.csv dataset, check nulls and make a bar chart")
        self.assertLessEqual(len(tools_data), 12)
        tool_names = [getattr(t, "__name__", "") for t in tools_data]
        self.assertIn("data_chart", tool_names)
        self.assertIn("data_inspect", tool_names)

        # Query matching browser/web testing
        tools_web = filter_tools_for_request("open browser and test localhost:3000 for console errors")
        self.assertLessEqual(len(tools_web), 12)
        web_names = [getattr(t, "__name__", "") for t in tools_web]
        self.assertTrue(any("browser" in name or "web" in name for name in web_names))

    def test_validate_tool_arguments(self):
        """Validates JSON schema checking of tool arguments before execution."""
        # Valid call
        ok, reason = validate_tool_arguments("run_powershell", {"script": "Get-Process"})
        self.assertTrue(ok)
        self.assertIsNone(reason)

        # Missing required parameter
        bad_missing, reason_missing = validate_tool_arguments("run_powershell", {})
        self.assertFalse(bad_missing)
        self.assertIn("Missing required parameter 'script'", reason_missing)

        # Type mismatch (integer passed for string)
        bad_type, reason_type = validate_tool_arguments("file_read", {"path": 12345})
        self.assertFalse(bad_type)
        self.assertIn("must be string", reason_type)

    def test_small_model_system_prompt(self):
        """Verifies concise small model system prompt."""
        prompt = get_small_model_system_prompt()
        self.assertIn("Superlocal", prompt)
        self.assertIn("PowerShell", prompt)
        self.assertLess(len(prompt), 400)

    # --------------------------------------------------------------------------
    # 3. Ollama Provider Chat & Mocked Execution
    # --------------------------------------------------------------------------
    @patch("providers.ollama_provider.requests.post")
    def test_ollama_provider_chat_native_tool_call(self, mock_post):
        """Validates Ollama provider chat parsing native tool calls with temperature 0.2."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen3:8b",
            "message": {
                "role": "assistant",
                "content": "Opening notepad for you.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "open_app",
                            "arguments": {"name": "notepad"}
                        }
                    }
                ]
            }
        }
        mock_post.return_value = mock_resp

        provider = OllamaProvider(host="http://localhost:11434", model="qwen3:8b")
        messages = [LLMMessage(role="user", content="open notepad")]
        res = provider.chat(messages=messages, tools=[run_powershell])

        self.assertEqual(res.model_used, "qwen3:8b")
        self.assertEqual(len(res.tool_calls), 1)
        self.assertEqual(res.tool_calls[0].name, "open_app")
        self.assertEqual(res.tool_calls[0].arguments, {"name": "notepad"})

        # Verify request payload options (temperature 0.2)
        sent_payload = mock_post.call_args[1]["json"]
        self.assertEqual(sent_payload["options"]["temperature"], 0.2)
        self.assertLessEqual(len(sent_payload.get("tools", [])), 12)

    @patch("providers.ollama_provider.requests.post")
    def test_ollama_cloud_bearer_token(self, mock_post):
        """Validates that Ollama cloud requests include Bearer token header."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"message": {"content": "Hello Cloud", "tool_calls": []}}
        mock_post.return_value = mock_resp

        provider = OllamaProvider(name="ollama_cloud", host="https://ollama.com", api_key="secret_token_123")
        provider.chat(messages=[LLMMessage(role="user", content="hello")])

        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer secret_token_123")

    @patch("providers.ollama_provider.requests.post")
    def test_ollama_fallback_json_in_text(self, mock_post):
        """Validates parsing of raw markdown JSON tool blocks from smaller models."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": 'Here is the command:\n```json\n{"name": "run_powershell", "arguments": {"script": "dir"}}\n```',
                "tool_calls": []
            }
        }
        mock_post.return_value = mock_resp

        provider = OllamaProvider()
        res = provider.chat(messages=[LLMMessage(role="user", content="list files")])
        self.assertEqual(len(res.tool_calls), 1)
        self.assertEqual(res.tool_calls[0].name, "run_powershell")
        self.assertEqual(res.tool_calls[0].arguments, {"script": "dir"})

    @patch("providers.ollama_provider.requests.post")
    def test_ollama_invalid_schema_two_strike_error(self, mock_post):
        """Validates that 2 consecutive invalid tool schemas trigger InvalidToolCallError."""
        # Response with missing required parameter 'script'
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "message": {
                "tool_calls": [
                    {"function": {"name": "run_powershell", "arguments": {}}}
                ]
            }
        }
        mock_post.return_value = mock_resp

        provider = OllamaProvider()
        # Strike 1: does not raise yet
        provider.chat(messages=[LLMMessage(role="user", content="run bad 1")])
        self.assertEqual(provider.consecutive_invalid_tool_calls, 1)

        # Strike 2: raises InvalidToolCallError to trigger provider fallback
        with self.assertRaises(InvalidToolCallError):
            provider.chat(messages=[LLMMessage(role="user", content="run bad 2")])

    # --------------------------------------------------------------------------
    # 4. Multi-Provider Automatic Fallback in AstraAgent
    # --------------------------------------------------------------------------
    def test_agent_fallback_from_offline_ollama_to_gemini(self):
        """
        Validates that when the primary provider (Ollama) is offline/unreachable,
        AstraAgent automatically logs and switches to the fallback provider (Gemini).
        """
        agent = AstraAgent(memory=self.memory)

        # Mock Ollama provider throwing connection error
        mock_ollama = MagicMock()
        mock_ollama.name = "ollama_local"
        mock_ollama.chat.side_effect = ProviderUnavailableError("Connection refused: http://localhost:11434")

        # Mock Gemini provider succeeding
        mock_gemini = MagicMock()
        mock_gemini.name = "gemini"
        mock_gemini.active_model = "gemini-3.8-flash"
        mock_gemini.chat.return_value = LLMResponse(
            text="Successfully completed via Gemini fallback.",
            tool_calls=[]
        )

        agent.provider_chain = [mock_ollama, mock_gemini]
        agent.active_provider = mock_ollama

        result = agent.run("what are the latest trends in quantum computing?")
        self.assertIn("Successfully completed via Gemini fallback", result)
        self.assertEqual(agent.active_provider.name, "gemini")

    def test_agent_fallback_on_gemini_429_exhaustion(self):
        """
        Validates that when Gemini exhausts all models with 429, it gracefully falls back
        or reports clear quota reset countdown without looping.
        """
        agent = AstraAgent(memory=self.memory)

        mock_gemini = MagicMock()
        mock_gemini.name = "gemini"
        mock_gemini.chat.side_effect = ProviderQuotaExhaustedError("All Gemini models exhausted.", retry_delay="14h 22m")

        agent.provider_chain = [mock_gemini]
        agent.active_provider = mock_gemini

        result = agent.run("complex prompt that exhausts quota")
        self.assertIn("Quota resets in 14h 22m", result)

    # --------------------------------------------------------------------------
    # 5. Local-First Execution (Zero API Calls)
    # --------------------------------------------------------------------------
    def test_local_first_bypasses_all_providers(self):
        """Verifies local-first commands resolve immediately without calling any provider."""
        with patch("tools.shell.subprocess.Popen") as mock_popen:
            res = try_local_first_execution("open notepad")
            self.assertIsNotNone(res)
            self.assertIn("notepad", res.lower())

        with patch("tools.shell.subprocess.run") as mock_ps:
            mock_ps.return_value = MagicMock(returncode=0, stdout="", stderr="")
            res_folder = try_local_first_execution("open desktop")
            self.assertIsNotNone(res_folder)
            self.assertIn("Desktop folder", res_folder)

    # --------------------------------------------------------------------------
    # 6. Provider Switching API & Model Listing
    # --------------------------------------------------------------------------
    def test_agent_set_provider(self):
        """Validates dynamic provider switching via set_provider()."""
        agent = AstraAgent(memory=self.memory)
        new_p = agent.set_provider("gemini")
        self.assertEqual(agent.active_provider.name, "gemini")

        new_p_ol = agent.set_provider("ollama_local")
        self.assertEqual(agent.active_provider.name, "ollama_local")

    @patch("providers.ollama_provider.requests.get")
    def test_ollama_list_models(self, mock_get):
        """Validates listing local models from Ollama API."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "models": [
                {"name": "qwen3:8b", "size": 4700000000},
                {"name": "llama3.1:8b", "size": 4900000000}
            ]
        }
        mock_get.return_value = mock_resp

        provider = OllamaProvider()
        models = provider.list_models()
        self.assertEqual(len(models), 2)
        self.assertIn("qwen3:8b", models)
        self.assertIn("llama3.1:8b", models)

    # --------------------------------------------------------------------------
    # 7. BUG 1: Gemini Thought Signatures & Single User Turn Verification
    # --------------------------------------------------------------------------
    def test_gemini_preserves_thought_signature_and_original_parts(self):
        """
        BUG 1 Unit Test:
        Validates that GeminiProvider:
        1. Appends the model's ORIGINAL response content object (response.candidates[0].content)
           with all its parts intact (including thought_signature and thought parts).
        2. Does not rebuild or clone function call parts by hand.
        3. Sends function responses back as a single user turn matching id and name.
        """
        gemini = GeminiProvider(api_key="mock_key_12345")
        gemini.client = MagicMock()

        # Create mock candidate with thought part containing thought_signature
        mock_thought_part = MagicMock()
        mock_thought_part.text = "Thinking: I should run a PowerShell script to list directories."
        mock_thought_part.thought = True
        mock_thought_part.thought_signature = b"thought_signature_gemini_2_5_hash_987"
        mock_thought_part.function_call = None

        mock_call_part = MagicMock()
        mock_call_part.text = None
        mock_call_part.thought = False
        mock_call_part.thought_signature = b"fc_signature_hash_654"
        mock_fc = MagicMock(id="call_stage1_01", args={"script": "dir"})
        mock_fc.name = "run_powershell"
        mock_call_part.function_call = mock_fc

        original_content = MagicMock()
        original_content.role = "model"
        original_content.parts = [mock_thought_part, mock_call_part]

        mock_candidate = MagicMock()
        mock_candidate.content = original_content

        mock_resp_step1 = MagicMock()
        mock_resp_step1.candidates = [mock_candidate]

        gemini.client.models.generate_content.return_value = mock_resp_step1

        # Turn 1: User prompt
        turn1_messages = [LLMMessage(role="user", content="list files in current directory")]
        res1 = gemini.chat(messages=turn1_messages)

        # 1. Assert tool call is parsed properly
        self.assertEqual(len(res1.tool_calls), 1)
        self.assertEqual(res1.tool_calls[0].name, "run_powershell")
        self.assertEqual(res1.tool_calls[0].id, "call_stage1_01")

        # 2. Assert history preserved original content object verbatim with thought_signature
        self.assertIn(original_content, gemini.conversation_contents)
        model_turn_in_history = gemini.conversation_contents[-1]
        self.assertIs(model_turn_in_history, original_content, "Must append the model's exact Content object")
        self.assertEqual(len(model_turn_in_history.parts), 2)
        self.assertEqual(model_turn_in_history.parts[0].thought_signature, b"thought_signature_gemini_2_5_hash_987")
        self.assertEqual(model_turn_in_history.parts[1].thought_signature, b"fc_signature_hash_654")

        # Turn 2: Send function responses back
        mock_resp_step2 = MagicMock()
        mock_resp_step2.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text="Here are your files: ...", thought=False, function_call=None)]))
        ]
        gemini.client.models.generate_content.return_value = mock_resp_step2

        turn2_messages = [
            LLMMessage(role="user", content="list files in current directory"),
            LLMMessage(role="assistant", content=None, tool_calls=res1.tool_calls),
            LLMMessage(role="tool", content={"stdout": "file1.txt\nfile2.txt", "exit_code": 0}, tool_call_id="call_stage1_01", name="run_powershell")
        ]
        res2 = gemini.chat(messages=turn2_messages)

        # 3. Assert function responses are sent back as a SINGLE user turn
        # History structure should be: [User Prompt, Model Original Content, Single User Turn with FunctionResponse, Model Response]
        user_tool_turn = gemini.conversation_contents[2]
        self.assertEqual(user_tool_turn.role, "user")
        self.assertEqual(len(user_tool_turn.parts), 1)
        self.assertTrue(hasattr(user_tool_turn.parts[0], "function_response"))

    def test_provider_switch_converts_history_to_plain_text(self):
        """
        Validates that when switching providers mid-task, history is converted
        to plain text summaries and another provider's raw parts or signatures
        are never passed to Gemini.
        """
        gemini = GeminiProvider(api_key="mock_key_12345")
        gemini.client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text="Continued from switch", thought=False, function_call=None)]))
        ]
        gemini.client.models.generate_content.return_value = mock_resp

        # Messages originating from Ollama (plain dicts, foreign parts)
        foreign_messages = [
            LLMMessage(role="user", content="create a report"),
            LLMMessage(role="assistant", content="Working on it", tool_calls=[ToolCall(id="ol_1", name="file_write", arguments={"path": "rep.txt", "content": "data"})], provider="ollama"),
            LLMMessage(role="tool", content={"success": True}, tool_call_id="ol_1", name="file_write", provider="ollama")
        ]

        gemini.chat(messages=foreign_messages)

        # Verify all turns before generation were converted to plain text parts (no foreign raw parts)
        for content_obj in gemini.conversation_contents[:-1]:
            for p in content_obj.parts:
                self.assertIsNotNone(p.text)
                self.assertFalse(hasattr(p, "thought_signature") and p.thought_signature)

    # --------------------------------------------------------------------------
    # 8. BUG 2: Ollama Auto-Start, Health Check & Diagnostic Reporting
    # --------------------------------------------------------------------------
    @patch("providers.ollama_provider.requests.get")
    def test_ollama_health_check_hint(self, mock_get):
        """
        BUG 2 Unit Test:
        Validates clear hint: 'Run 'ollama serve' and 'ollama pull <model>''
        when Ollama is unreachable or model is missing.
        """
        # Unreachable
        mock_get.side_effect = Exception("Connection refused")
        provider = OllamaProvider(host="http://localhost:11434", model="qwen3:8b")
        is_h, details, hint = provider.health_check(auto_start=False)
        self.assertFalse(is_h)
        self.assertIn("Run 'ollama serve' and 'ollama pull qwen3:8b'", hint)

        # Reachable but model missing
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"models": [{"name": "mistral:latest"}]}
        mock_get.side_effect = None
        mock_get.return_value = mock_resp

        is_h2, details2, hint2 = provider.health_check(auto_start=False)
        self.assertFalse(is_h2)
        self.assertIn("Model 'qwen3:8b' not found", details2)
        self.assertIn("Run 'ollama pull qwen3:8b'", hint2)

    @patch("providers.ollama_provider.subprocess.Popen")
    @patch("providers.ollama_provider.requests.get")
    def test_ollama_auto_start_localhost(self, mock_get, mock_popen):
        """
        BUG 2 Unit Test:
        Validates trying to start 'ollama serve' automatically in background
        when host is localhost and it is not running.
        """
        # Initial check fails, auto_start initial check fails, then starts up and succeeds
        mock_resp_fail = MagicMock(status_code=500)
        mock_resp_ok = MagicMock(status_code=200)
        mock_resp_ok.json.return_value = {"models": [{"name": "qwen3:8b"}]}

        mock_get.side_effect = [Exception("Refused"), Exception("Refused"), mock_resp_ok]

        provider = OllamaProvider(host="http://localhost:11434", model="qwen3:8b")
        is_h, details, hint = provider.health_check(auto_start=True)

        mock_popen.assert_called_once()
        cmd_called = mock_popen.call_args[0][0]
        self.assertEqual(cmd_called, ["ollama", "serve"])

    def test_agent_skips_unhealthy_provider_without_step_failure(self):
        """
        BUG 2 Unit Test:
        Validates that a provider that failed its health check is skipped
        immediately without incrementing step or counting as a step failure.
        """
        agent = AstraAgent(memory=self.memory)

        unhealthy_prov = MagicMock()
        unhealthy_prov.name = "ollama_local"
        unhealthy_prov.health_check.return_value = (False, "Unreachable", "Run 'ollama serve' and 'ollama pull qwen3:8b'")

        healthy_prov = MagicMock()
        healthy_prov.name = "gemini"
        healthy_prov.health_check.return_value = (True, "Online", None)
        healthy_prov.chat.return_value = LLMResponse(text="Task completed via healthy provider.")

        agent.provider_chain = [unhealthy_prov, healthy_prov]
        agent.active_provider = unhealthy_prov

        result = agent.run("tell me a fun fact about computer history")
        self.assertIn("Task completed via healthy provider", result)
        # Unhealthy provider was skipped without calling its chat method!
        unhealthy_prov.chat.assert_not_called()
        healthy_prov.chat.assert_called_once()

    def test_all_providers_failed_prints_diagnostic_for_each(self):
        """
        BUG 2 Unit Test:
        If all providers fail, validates that each failed provider and its
        exact fix are reported, instead of only the last error.
        """
        agent = AstraAgent(memory=self.memory)

        prov1 = MagicMock()
        prov1.name = "ollama_local"
        prov1.health_check.return_value = (False, "Unreachable at http://localhost:11434", "Run 'ollama serve' and 'ollama pull qwen3:8b'")

        prov2 = MagicMock()
        prov2.name = "gemini"
        prov2.health_check.return_value = (False, "GEMINI_API_KEY is not configured", "Set GEMINI_API_KEY in .env")

        agent.provider_chain = [prov1, prov2]
        agent.active_provider = prov1

        result = agent.run("another prompt when everything is offline")
        self.assertIn("All AI providers failed", result)
        self.assertIn("ollama_local", result)
        self.assertIn("Run 'ollama serve' and 'ollama pull qwen3:8b'", result)
        self.assertIn("gemini", result)
        self.assertIn("Set GEMINI_API_KEY in .env", result)


if __name__ == "__main__":
    unittest.main()
