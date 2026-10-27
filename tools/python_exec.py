"""
Astra-Local Python Code Runner
Executes arbitrary Python code in an isolated subprocess with timeout and stdout/stderr capture.
"""

import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any
from config import PYTHON_TIMEOUT


def run_python(code: str, timeout: int = PYTHON_TIMEOUT) -> Dict[str, Any]:
    """
    Executes a Python code string using the active Python interpreter.
    Writes code to a temporary script and captures execution results.
    """
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            temp_file = Path(f.name)

        proc = subprocess.run(
            [sys.executable, str(temp_file)],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "exit_code": proc.returncode,
            "success": proc.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Python execution timed out after {timeout} seconds.",
            "exit_code": -1,
            "success": False
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Python execution failed: {str(e)}",
            "exit_code": -1,
            "success": False
        }
    finally:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
