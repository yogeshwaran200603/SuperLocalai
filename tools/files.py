"""
Astra-Local File System Tools
Provides file_read, file_write, file_list, file_move, and file_delete
with safety boundaries and path expansion.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
from safety import is_path_allowed


def _resolve(path_str: str) -> Path:
    """Expands environment variables and resolves to absolute path."""
    expanded = os.path.expandvars(path_str)
    return Path(expanded).resolve()


def file_read(path: str, max_lines: int = 1000) -> Dict[str, Any]:
    """Reads content from a text file up to max_lines."""
    target = _resolve(path)
    if not target.exists():
        return {"success": False, "error": f"File does not exist: {target}"}
    if not target.is_file():
        return {"success": False, "error": f"Path is not a file: {target}"}

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(max_lines)]
            content = "".join(lines)
            return {
                "success": True,
                "path": str(target),
                "lines_read": len(lines),
                "content": content
            }
    except Exception as e:
        return {"success": False, "error": str(e), "path": str(target)}


def file_write(path: str, content: str, mode: str = "write") -> Dict[str, Any]:
    """Writes or appends text content to a file."""
    target = _resolve(path)
    if not is_path_allowed(str(target)):
        return {"success": False, "error": f"Access denied: Path '{target}' is outside allowed directories."}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_mode = "a" if mode.lower() == "append" else "w"
        with open(target, write_mode, encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "path": str(target),
            "bytes_written": len(content.encode("utf-8")),
            "mode": mode,
            "message": f"Successfully wrote to {target}"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "path": str(target)}


def file_list(path: str = ".", recursive: bool = False) -> Dict[str, Any]:
    """Lists files and directories in a given path."""
    target = _resolve(path)
    if not target.exists():
        return {"success": False, "error": f"Path does not exist: {target}"}

    try:
        entries = []
        if recursive:
            for root, dirs, files in os.walk(target):
                for d in dirs:
                    entries.append({"name": d, "type": "dir", "path": str(Path(root) / d)})
                for f in files:
                    p = Path(root) / f
                    entries.append({"name": f, "type": "file", "path": str(p), "size": p.stat().st_size})
        else:
            for item in target.iterdir():
                entries.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "path": str(item),
                    "size": item.stat().st_size if item.is_file() else None
                })
        return {
            "success": True,
            "path": str(target),
            "count": len(entries),
            "entries": entries[:200]  # Cap to prevent huge prompt payloads
        }
    except Exception as e:
        return {"success": False, "error": str(e), "path": str(target)}


def file_move(src: str, dest: str) -> Dict[str, Any]:
    """Moves or renames a file or directory."""
    source_path = _resolve(src)
    dest_path = _resolve(dest)
    if not is_path_allowed(str(source_path)):
        return {"success": False, "error": f"Access denied: Source path '{source_path}' is outside allowed directories."}
    if not is_path_allowed(str(dest_path)):
        return {"success": False, "error": f"Access denied: Destination path '{dest_path}' is outside allowed directories."}
    if not source_path.exists():
        return {"success": False, "error": f"Source does not exist: {source_path}"}

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(dest_path))
        return {
            "success": True,
            "source": str(source_path),
            "destination": str(dest_path),
            "message": f"Moved {source_path} to {dest_path}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def file_delete(path: str) -> Dict[str, Any]:
    """Deletes a file or directory permanently."""
    target = _resolve(path)
    if not is_path_allowed(str(target)):
        return {"success": False, "error": f"Access denied: Path '{target}' is outside allowed directories."}
    if not target.exists():
        return {"success": False, "error": f"Target does not exist: {target}"}

    try:
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
        return {
            "success": True,
            "path": str(target),
            "message": f"Deleted {target}"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "path": str(target)}
