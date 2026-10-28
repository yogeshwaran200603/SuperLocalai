"""
Astra-Local Python Code Runner
Executes arbitrary Python code in an isolated subprocess with timeout and stdout/stderr capture.
"""

import sys
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any
from config import PYTHON_TIMEOUT
from safety import is_emergency_stopped


def run_python(code: str, timeout: int = PYTHON_TIMEOUT) -> Dict[str, Any]:
    """
    Executes a Python code string using the active Python interpreter.
    Writes code to a temporary script and captures execution results.
    Interrupts immediately if emergency stop (Ctrl+Alt+Q) is triggered.
    """
    if is_emergency_stopped():
        return {
            "stdout": "",
            "stderr": "Execution cancelled: Emergency stop (Ctrl+Alt+Q) active.",
            "exit_code": -1,
            "success": False,
        }

    temp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            temp_file = Path(f.name)

        proc = subprocess.Popen(
            [sys.executable, str(temp_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        start_time = time.time()
        while proc.poll() is None:
            if is_emergency_stopped():
                proc.kill()
                return {
                    "stdout": "",
                    "stderr": "Execution cancelled: Emergency stop (Ctrl+Alt+Q) triggered.",
                    "exit_code": -1,
                    "success": False,
                }
            if time.time() - start_time > timeout:
                proc.kill()
                return {
                    "stdout": "",
                    "stderr": f"Python execution timed out after {timeout} seconds.",
                    "exit_code": -1,
                    "success": False,
                }
            time.sleep(0.05)

        stdout, stderr = proc.communicate()
        return {
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Python execution failed: {str(e)}",
            "exit_code": -1,
            "success": False,
        }
    finally:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
