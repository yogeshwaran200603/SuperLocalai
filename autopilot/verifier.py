"""
SuperLocal Autopilot: Verifier and Self-Healing Engine
Verifies outcomes after each step:
- Code: tests pass, syntax valid (ast.parse), exit code zero
- Web: Playwright console errors, HTTP failures, UI renders
- Files: created files exist and are not empty (> 0 bytes)
Supports up to 3 self-healing retries before prompting the user.
"""

import os
import ast
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List, Callable

from autopilot.state import JobStep


class AutopilotVerifier:
    """
    Validates step results and drives the self-healing loop.
    """

    def verify_step(
        self,
        step: JobStep,
        workspace_dir: Path,
        result: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Validates the outcome of a step.
        Returns: (passed: bool, message: str)
        """
        res = result or step.result or {}

        # 1. Explicit failure flag in result
        check_type = step.success_check
        if res.get("success") is False:
            err = res.get("error") or res.get("stderr") or res.get("stdout") or "Step explicitly returned failure"
            if step.tool == "run_tests" or check_type == "tests_pass":
                return False, f"Tests failed to pass:\n{err}"
            return False, f"Execution failed: {err}"

        # 2. Files existence check
        check_type = step.success_check
        if check_type in ("files_exist", "file_exists") or step.tool in ("scaffold_project", "file_write"):
            # Check target files
            files_to_check: List[str] = []
            if "path" in step.args:
                files_to_check.append(step.args["path"])
            if "files" in step.args and isinstance(step.args["files"], list):
                files_to_check.extend(step.args["files"])
            if "files_created" in res and isinstance(res["files_created"], list):
                files_to_check.extend(res["files_created"])
            if "file" in res:
                files_to_check.append(res["file"])

            # Default checks for scaffolding
            if step.tool == "scaffold_project" and not files_to_check:
                # Minimum viable project files
                files_to_check = ["README.md"]

            for fpath in files_to_check:
                p = Path(fpath)
                target = p if p.is_absolute() else (workspace_dir / p)
                if not target.exists():
                    return False, f"Expected file does not exist: {target.name}"
                if target.is_file() and target.stat().st_size == 0:
                    return False, f"File was created but is empty (0 bytes): {target.name}"

                # If Python file, verify syntax
                if target.suffix == ".py":
                    try:
                        code = target.read_text(encoding="utf-8")
                        ast.parse(code)
                    except SyntaxError as syn_err:
                        return False, f"Python syntax error in {target.name} (line {syn_err.lineno}): {syn_err.msg}"
                    except Exception as e:
                        return False, f"Error validating Python code in {target.name}: {str(e)}"

        # 3. Exit code check for scripts / shell
        if check_type == "exit_code_zero" or step.tool in ("run_powershell", "run_command", "shell_exec"):
            exit_code = res.get("exit_code")
            if exit_code is not None and exit_code != 0:
                stderr = res.get("stderr", "").strip()
                stdout = res.get("stdout", "").strip()
                return False, f"Process exited with non-zero code {exit_code}: {stderr or stdout or 'no output'}"

        # 4. Test suite validation
        if check_type == "tests_pass" or step.tool == "run_tests":
            exit_code = res.get("exit_code", 0)
            stdout = res.get("stdout", "")
            stderr = res.get("stderr", "")
            combined = (stdout + "\n" + stderr).lower()
            if exit_code != 0 or "failed" in combined or "error" in combined and "passed" not in combined:
                return False, f"Tests failed to pass:\n{stderr or stdout}"

        # 5. Web application / browser console check
        if check_type == "no_console_errors" or step.tool == "test_website":
            console_errors = res.get("console_errors", [])
            if console_errors:
                return False, f"Browser console errors detected: {'; '.join(console_errors[:3])}"
            failed_requests = res.get("failed_requests", [])
            if failed_requests:
                return False, f"Failed network requests detected: {failed_requests[:2]}"

        return True, "Verification succeeded"

    def heal_step(
        self,
        step: JobStep,
        workspace_dir: Path,
        failure_reason: str,
        executor_func: Callable[[JobStep, Path], Dict[str, Any]],
        provider: Optional[Any] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Attempts up to 3 self-healing iterations for a failing step.
        Returns: (success: bool, final_result: dict)
        """
        max_retries = 3

        while step.retry_count < max_retries:
            step.retry_count += 1
            print(f"[Autopilot Self-Heal] Retry {step.retry_count}/{max_retries} for step {step.id} ({step.tool}): {failure_reason}")

            # Attempt self-healing logic
            healed_args = dict(step.args)

            # Heuristic 1: If file was missing, attempt creation
            if "Expected file does not exist" in failure_reason:
                missing_filename = failure_reason.split(":")[-1].strip()
                target_file = workspace_dir / missing_filename
                if not target_file.exists():
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(f"# {missing_filename}\nCreated by self-healing agent.\n", encoding="utf-8")

            # Heuristic 2: Python syntax error repair
            elif "Python syntax error" in failure_reason:
                for py_file in workspace_dir.glob("**/*.py"):
                    try:
                        content = py_file.read_text(encoding="utf-8")
                        ast.parse(content)
                    except SyntaxError:
                        # Attempt basic repair if model provider is available
                        if provider:
                            try:
                                prompt = f"Fix the Python syntax error in this file:\n\n{content}\nReturn ONLY the fixed python code."
                                fixed = provider.chat(prompt).text.strip()
                                if fixed.startswith("```"):
                                    fixed = fixed.split("```")[1]
                                    if fixed.startswith("python"):
                                        fixed = fixed[6:]
                                py_file.write_text(fixed.strip(), encoding="utf-8")
                            except Exception:
                                pass

            # Re-run execution
            result = executor_func(step, workspace_dir)
            passed, reason = self.verify_step(step, workspace_dir, result)
            if passed:
                return True, result
            failure_reason = reason

        return False, {"success": False, "error": f"Self-healing exhausted {max_retries} retries: {failure_reason}"}
