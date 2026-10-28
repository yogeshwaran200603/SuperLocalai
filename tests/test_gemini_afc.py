"""
AST test to verify that automatic_function_calling is disabled in EVERY Gemini generate_content call.
Prevents SDK multi-turn recursion bugs, schema drop issues, and ensures thought_signature preservation.
"""

import ast
from pathlib import Path
import pytest


def find_python_files(root_dir: Path):
    for p in root_dir.rglob("*.py"):
        # Ignore virtual environments, git, cache, and test files themselves
        parts = [part.lower() for part in p.parts]
        if any(ign in parts for ign in (".git", "venv", ".venv", "__pycache__", "build", "dist", "tests")):
            continue
        yield p


def test_every_gemini_call_disables_automatic_function_calling():
    """
    Scans every non-test Python file in the codebase.
    Any call to `generate_content` MUST pass a config that disables automatic function calling.
    """
    repo_root = Path(__file__).resolve().parent.parent
    py_files = list(find_python_files(repo_root))

    assert len(py_files) > 10, f"Found only {len(py_files)} files to check"

    calls_found = 0
    violations = []

    for py_file in py_files:
        src = py_file.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_gen_content = False
                if isinstance(func, ast.Attribute) and func.attr == "generate_content":
                    is_gen_content = True

                if is_gen_content:
                    calls_found += 1
                    # Verify that in this file/function, AutomaticFunctionCallingConfig(disable=True) is used
                    rel_path = py_file.relative_to(repo_root)
                    line_no = node.lineno

                    # Check that config keyword is passed to generate_content
                    has_config_arg = any(kw.arg == "config" for kw in node.keywords)
                    if not has_config_arg:
                        violations.append(f"{rel_path}:{line_no} calls generate_content without config parameter")
                        continue

                    # Check that the file source around this call configures disable=True
                    lines = src.splitlines()
                    start_scan = max(0, line_no - 120)
                    window_src = "\n".join(lines[start_scan:line_no])
                    if "AutomaticFunctionCallingConfig(disable=True)" not in window_src and "disable=True" not in window_src:
                        violations.append(f"{rel_path}:{line_no} does not set AutomaticFunctionCallingConfig(disable=True)")

    assert calls_found >= 5, f"Expected at least 5 generate_content calls in repo, found {calls_found}"
    assert not violations, f"Gemini generate_content calls lacking disable=True found:\n" + "\n".join(violations)
