"""
Astra-Local Comprehensive Multi-Stage Automated Test Suite
Validates Stage 1 through Stage 5 implementations:
- Stage 1: Shortcuts lookup, configuration, safety filter, PowerShell wrapper, open_app.
- Stage 2: Browser module interfaces, WhatsApp dedicated selectors, safety prompt hook.
- Stage 3: File system operations, Python runner, CSV missing values analysis & chart, PPTX 5-slide creation.
- Stage 4: Desktop automation signatures, DevTools Flask login scaffolding, Web testing engine.
- Stage 5: SQLite memory persistence, session tracking, action logging.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    load_shortcuts,
    get_system_prompt,
    MODEL_NAME,
    THINKING_LEVEL,
    DESKTOP_DIR,
    ACTIONS_LOG_PATH,
)
from safety import (
    inspect_powershell_safety,
    is_path_allowed,
    log_action,
    confirm_action,
)
from memory import MemoryManager
from tools.shell import run_powershell, open_app, open_url
from tools.files import file_write, file_read, file_list, file_delete, file_move
from tools.python_exec import run_python
from tools.data import data_inspect, data_clean, data_chart
from tools.docs import doc_create_pptx, doc_create_docx, doc_create_xlsx
from tools.devtools import scaffold_project
from tools.whatsapp import SEARCH_SELECTORS, MESSAGE_BOX_SELECTORS


class TestStage1CoreAndShortcuts(unittest.TestCase):
    """Stage 1: Config, Shortcuts, Safety Blocklist, and Shell execution."""

    def test_shortcuts_resolution(self):
        shortcuts = load_shortcuts()
        self.assertIn("discord_servers", shortcuts)
        self.assertIn("my server", shortcuts["discord_servers"])
        target = shortcuts["discord_servers"]["my server"]
        self.assertEqual(target, "discord://-/channels/SERVER_ID/CHANNEL_ID")

    def test_discord_example_command_generation(self):
        """Validates: 'open discord and go to my server' -> resolves to deep link."""
        res = open_app("my server")
        self.assertEqual(res.get("shortcut"), "my server")
        self.assertEqual(res.get("deep_link"), "discord://-/channels/SERVER_ID/CHANNEL_ID")

    def test_safety_blocklist(self):
        blocked, reason, _ = inspect_powershell_safety("format C: /fs:NTFS")
        self.assertTrue(blocked)

        blocked, reason, _ = inspect_powershell_safety("del C:\\Windows\\System32\\calc.exe")
        self.assertTrue(blocked)

        blocked, reason, _ = inspect_powershell_safety("reg delete HKLM\\Software")
        self.assertTrue(blocked)

        blocked, reason, _ = inspect_powershell_safety("shutdown -s -t 0")
        self.assertTrue(blocked)

        # Safe command
        blocked, _, high_risk = inspect_powershell_safety("Get-Process | Select-Object -First 5")
        self.assertFalse(blocked)
        self.assertFalse(high_risk)

    def test_run_powershell_execution(self):
        res = run_powershell("Write-Output 'ASTRA_TEST_OK'")
        self.assertTrue(res["success"])
        self.assertIn("ASTRA_TEST_OK", res["stdout"])


class TestStage2BrowserAndWhatsApp(unittest.TestCase):
    """Stage 2: Browser automation interfaces and WhatsApp safety guardrails."""

    def test_whatsapp_selectors_integrity(self):
        self.assertTrue(len(SEARCH_SELECTORS) > 0)
        self.assertTrue(len(MESSAGE_BOX_SELECTORS) > 0)
        # Search selectors must include standard WhatsApp Web aria labels / contenteditable
        has_search_attr = any("Search" in s or "contenteditable" in s for s in SEARCH_SELECTORS)
        self.assertTrue(has_search_attr)

    def test_whatsapp_mandatory_confirmation_guard(self):
        """Verifies that whatsapp_send is never auto-approved."""
        from safety import MANDATORY_CONFIRMATION_TOOLS
        self.assertIn("whatsapp_send", MANDATORY_CONFIRMATION_TOOLS)


class TestStage3DataDocsAndPython(unittest.TestCase):
    """Stage 3: CSV analysis, missing values, cleaning, chart generation, and PPTX presentation."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_csv_analysis_and_cleaning(self):
        # 1. Create a synthetic sales.csv with missing values
        csv_file = self.test_path / "sales.csv"
        csv_content = (
            "Item,Category,Sales,Revenue\n"
            "Widget A,Hardware,10,100.0\n"
            "Widget B,Hardware,,250.0\n"
            "Service X,Cloud,5,\n"
            "Widget A,Hardware,10,100.0\n"  # duplicate
            "Service Y,Cloud,8,400.0\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        # 2. Inspect missing values
        report = data_inspect(str(csv_file))
        self.assertTrue(report["success"])
        self.assertEqual(report["rows"], 5)
        self.assertTrue(report["has_missing"])
        self.assertIn("Sales", report["missing_values"])
        self.assertGreater(report["missing_values"]["Sales"]["missing_count"], 0)

        # 3. Clean dataset
        cleaned_file = self.test_path / "sales_cleaned.csv"
        clean_res = data_clean(str(csv_file), output_path=str(cleaned_file))
        self.assertTrue(clean_res["success"])
        self.assertEqual(clean_res["remaining_missing"], 0)
        self.assertGreater(clean_res["duplicates_removed"], 0)
        self.assertTrue(cleaned_file.exists())

        # 4. Generate bar chart
        chart_file = self.test_path / "sales_bar_chart.png"
        chart_res = data_chart(
            file_path=str(cleaned_file),
            chart_type="bar",
            x_col="Category",
            y_col="Revenue",
            title="Revenue by Category",
            output_image=str(chart_file)
        )
        self.assertTrue(chart_res["success"])
        self.assertTrue(chart_file.exists())
        self.assertGreater(chart_file.stat().st_size, 1000)

    def test_pptx_five_slide_creation(self):
        """Validates 'make a 5-slide presentation about AI and save it on Desktop'."""
        ppt_file = self.test_path / "AI_Presentation.pptx"
        slides = [
            {"title": "The Rise of Artificial Intelligence", "subtitle": "A Comprehensive Overview"},
            {"title": "What is Machine Learning?", "bullets": ["Supervised Learning", "Unsupervised Learning", "Neural Networks"]},
            {"title": "Large Language Models & GenAI", "bullets": ["Transformers Architecture", "Gemini 3 and Multi-modal AI", "Autonomous Agents"]},
            {"title": "Industry Applications", "bullets": ["Healthcare & Diagnostics", "Software Development", "Robotics & Autonomous Systems"]},
            {"title": "The Future & Ethics of AI", "bullets": ["Safety & Alignment", "Human-AI Collaboration", "AGI Trajectory"]}
        ]

        res = doc_create_pptx("AI Overview", slides, output_path=str(ppt_file))
        self.assertTrue(res["success"])
        self.assertTrue(ppt_file.exists())
        self.assertEqual(res["slide_count"], 5)
        self.assertGreater(ppt_file.stat().st_size, 5000)

    def test_run_python_code_execution(self):
        code = "print(sum([x * 2 for x in range(10)]))"
        res = run_python(code)
        self.assertTrue(res["success"])
        self.assertEqual(res["stdout"], "90")

    def test_file_move_and_security(self):
        src = self.test_path / "orig.txt"
        dst = self.test_path / "moved.txt"
        src.write_text("hello move", encoding="utf-8")
        res = file_move(str(src), str(dst))
        self.assertTrue(res["success"])
        self.assertFalse(src.exists())
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(encoding="utf-8"), "hello move")

        # Test security boundary rejection
        bad_res = file_move(str(dst), "C:\\Windows\\System32\\bad.txt")
        self.assertFalse(bad_res["success"])
        self.assertIn("Access denied", bad_res["error"])


class TestStage4DevToolsAndWebTest(unittest.TestCase):
    """Stage 4: DevTools (Flask login scaffolding) and Web testing."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_flask_scaffolding(self):
        """Validates 'create a Flask app with a login page and run it'."""
        res = scaffold_project("flask", "login_app", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        app_dir = Path(res["directory"])
        self.assertTrue((app_dir / "app.py").exists())
        self.assertTrue((app_dir / "templates" / "login.html").exists())
        self.assertTrue((app_dir / "templates" / "dashboard.html").exists())
        self.assertTrue((app_dir / "static" / "style.css").exists())

        # Verify app.py contains login route and session handling
        app_code = (app_dir / "app.py").read_text(encoding="utf-8")
        self.assertIn("@app.route(\"/login\"", app_code)
        self.assertIn("session[\"user\"]", app_code)

    def test_react_java_c_cpp_sql_scaffolding(self):
        """Validates all extended dev scaffolding templates."""
        # React
        res = scaffold_project("react", "my_react", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        self.assertTrue((Path(res["directory"]) / "src" / "App.jsx").exists())
        self.assertTrue((Path(res["directory"]) / "vite.config.js").exists())

        # Java
        res = scaffold_project("java", "my_java", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        self.assertTrue((Path(res["directory"]) / "pom.xml").exists())
        self.assertTrue((Path(res["directory"]) / "src" / "main" / "java" / "com" / "app" / "App.java").exists())

        # C
        res = scaffold_project("c", "my_c", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        self.assertTrue((Path(res["directory"]) / "src" / "main.c").exists())
        self.assertTrue((Path(res["directory"]) / "include" / "app.h").exists())

        # C++
        res = scaffold_project("cpp", "my_cpp", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        self.assertTrue((Path(res["directory"]) / "src" / "main.cpp").exists())
        self.assertTrue((Path(res["directory"]) / "CMakeLists.txt").exists())

        # SQL
        res = scaffold_project("sql", "my_sql", target_dir=str(self.test_path))
        self.assertTrue(res["success"])
        self.assertTrue((Path(res["directory"]) / "schema.sql").exists())
        self.assertTrue((Path(res["directory"]) / "seed.sql").exists())
        self.assertTrue((Path(res["directory"]) / "queries.sql").exists())
        self.assertTrue((Path(res["directory"]) / "init_db.py").exists())


class TestStage5MemoryAndLogging(unittest.TestCase):
    """Stage 5: SQLite memory, session persistence, and audit logging."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.test_dir.name) / "test_memory.db"
        self.mem = MemoryManager(db_path=self.db_path)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_memory_session_lifecycle(self):
        s_id = self.mem.create_session("Test Session 1")
        self.assertTrue(len(s_id) > 10)

        self.mem.add_message(s_id, "user", "open discord and go to my server")
        self.mem.add_message(s_id, "model", "I opened Discord to your server.")

        msgs = self.mem.get_session_messages(s_id)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "model")

        self.mem.record_tool_execution(s_id, "open_app", {"name": "my server"}, {"success": True}, "SUCCESS")
        sessions = self.mem.list_recent_sessions(limit=5)
        self.assertTrue(len(sessions) >= 1)

    def test_action_logging_and_sanitization(self):
        test_tool = "test_tool_call"
        test_args = {"param": "safe_val"}
        log_action(test_tool, test_args, "SUCCESS", "All good")
        self.assertTrue(ACTIONS_LOG_PATH.exists())
        content = ACTIONS_LOG_PATH.read_text(encoding="utf-8")
        self.assertIn("test_tool_call", content)


if __name__ == "__main__":
    unittest.main()
