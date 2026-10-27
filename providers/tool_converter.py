"""
Astra-Local Tool Schema Converter & Small-Model Optimizer
Converts Python tool functions into standard OpenAPI/JSON schema formats,
filters tools by keyword relevance (capping at 12 tools for small models),
and validates arguments against schema definitions before execution.
"""

import inspect
from typing import get_origin, get_args, Union, List, Dict, Any, Optional, Callable, Tuple
from tools import TOOL_REGISTRY


# Mapping of tools to descriptive relevance keywords for intelligent filtering
TOOL_TAGS: Dict[str, List[str]] = {
    # Shell & OS
    "run_powershell": ["powershell", "ps", "cmd", "command", "script", "terminal", "exec", "run", "process", "kill", "system"],
    "open_url": ["url", "link", "web", "http", "https", "browser", "site", "open"],
    "open_app": ["app", "application", "launch", "open", "program", "start", "shortcut"],
    
    # Browser
    "browser_goto": ["browse", "browser", "chrome", "navigate", "goto", "web", "site", "page", "url", "open"],
    "browser_click": ["browser", "click", "button", "element", "selector", "web", "link"],
    "browser_type": ["browser", "type", "input", "fill", "text", "web", "form"],
    "browser_press": ["browser", "press", "enter", "key", "keyboard", "web"],
    "browser_read_text": ["browser", "read", "text", "extract", "content", "web", "page", "scrape"],
    "browser_screenshot": ["browser", "screenshot", "capture", "image", "snap", "web"],
    "browser_wait_for": ["browser", "wait", "element", "load", "web"],
    
    # WhatsApp
    "whatsapp_send": ["whatsapp", "chat", "message", "send", "text", "amma", "contact", "wa"],
    
    # Desktop
    "desktop_screenshot": ["screenshot", "screen", "capture", "snap", "display", "image", "look"],
    "desktop_click": ["desktop", "click", "mouse", "double-click", "right-click", "tap", "press", "ui"],
    "desktop_type": ["desktop", "type", "keyboard", "keys", "input", "write", "note", "notepad"],
    "desktop_hotkey": ["hotkey", "shortcut", "keys", "press", "ctrl", "alt", "enter"],
    "desktop_focus_window": ["focus", "window", "switch", "activate", "bring", "foreground"],
    "desktop_locate_element": ["locate", "find", "button", "icon", "element", "screen", "vision"],
    
    # Files
    "file_read": ["file", "read", "open", "cat", "view", "lines", "check", "content"],
    "file_write": ["file", "write", "save", "create", "append", "note", "text", "make"],
    "file_list": ["file", "list", "dir", "directory", "folder", "ls", "find", "search", "downloads", "desktop"],
    "file_move": ["file", "move", "rename", "transfer", "mv", "copy"],
    "file_delete": ["file", "delete", "remove", "rm", "clean", "trash"],
    
    # Python
    "run_python": ["python", "py", "script", "code", "run", "execute", "calc", "math"],
    
    # Data
    "data_inspect": ["data", "csv", "inspect", "columns", "shape", "head", "dataset", "table", "sales"],
    "data_clean": ["data", "clean", "nulls", "missing", "impute", "drop", "nan", "csv"],
    "data_chart": ["chart", "plot", "graph", "bar", "histogram", "scatter", "matplotlib", "visualize", "data", "csv"],
    "data_train_model": ["train", "model", "predict", "ml", "machine", "learning", "scikit", "regression", "classification"],
    
    # Docs
    "doc_create_pptx": ["presentation", "slide", "slides", "pptx", "powerpoint", "deck"],
    "doc_create_docx": ["doc", "docx", "word", "document", "report", "notes"],
    "doc_create_xlsx": ["excel", "xlsx", "sheet", "spreadsheet", "table", "cells"],
    "doc_create_pdf": ["pdf", "report", "invoice", "document", "export"],
    
    # Dev
    "scaffold_project": ["scaffold", "flask", "react", "template", "project", "app", "create", "setup"],
    "run_tests": ["test", "tests", "pytest", "unit", "run", "verify", "suite"],
    "fix_and_rerun": ["fix", "patch", "repair", "debug", "rerun", "refactor"],
    
    # Webtest
    "test_website": ["audit", "test", "website", "localhost", "ui", "console", "bugs", "broken"],

    # Desktop Non-Vision & Quick Switcher
    "discord_goto": ["discord", "channel", "server", "goto", "chat", "dm", "message"],
    "get_screen_text": ["screen", "window", "windows", "title", "controls", "ui", "text", "inspect", "active"],

    # Chess
    "chess_benchmark": ["chess", "stockfish", "benchmark", "elo", "engine", "ladder"],
    "chess_analyze_pgn": ["chess", "pgn", "analyze", "blunder", "accuracy", "chart", "eval"],
    "chess_play_bot": ["chess", "bot", "computer", "play"]
}

# Essential core fallback tools always kept within selection priority
CORE_TOOLS = ["run_powershell", "open_app", "open_url", "file_read", "file_write"]


def _type_to_schema(annotation: Any) -> Dict[str, Any]:
    """Converts a Python type annotation to an OpenAPI JSON schema property."""
    if annotation == inspect.Parameter.empty:
        return {"type": "string"}
    
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if args:
            return _type_to_schema(args[0])
        return {"type": "string"}
    
    if origin in (list, List):
        args = get_args(annotation)
        item_schema = _type_to_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}
    
    if origin in (dict, Dict):
        return {"type": "object"}
    
    if annotation is str or annotation == "str":
        return {"type": "string"}
    if annotation is int or annotation == "int":
        return {"type": "integer"}
    if annotation is float or annotation == "float":
        return {"type": "number"}
    if annotation is bool or annotation == "bool":
        return {"type": "boolean"}
    
    return {"type": "string"}


def func_to_schema(func: Callable) -> Dict[str, Any]:
    """
    Transforms a Python callable into OpenAI / Ollama compatible JSON tool schema:
    {
      "type": "function",
      "function": {
        "name": ...,
        "description": ...,
        "parameters": {...}
      }
    }
    """
    sig = inspect.signature(func)
    doc = inspect.getdoc(func) or ""
    desc = doc.strip().split("\n\n")[0].replace("\n", " ")
    
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, param in sig.parameters.items():
        properties[name] = _type_to_schema(param.annotation)
        # Determine if required: parameter has no default and is not Optional
        if param.default == inspect.Parameter.empty:
            origin = get_origin(param.annotation)
            if origin is not Union or type(None) not in get_args(param.annotation):
                required.append(name)

    return {
        "type": "function",
        "function": {
            "name": getattr(func, "__name__", str(func)),
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def filter_tools_for_request(
    query: str,
    all_tools: Optional[List[Callable]] = None,
    max_tools: int = 12
) -> List[Callable]:
    """
    Selects at most `max_tools` (default 12) from available tools based on keyword relevance.
    Tailored for smaller local models (e.g. 7B/8B) that struggle with large tool sets.
    """
    if all_tools is None:
        tool_callables = list(TOOL_REGISTRY.values())
    else:
        tool_callables = all_tools

    # Extract clean tokens from query
    clean_query = query.lower().replace(",", " ").replace(".", " ").replace("/", " ")
    query_tokens = set(clean_query.split())

    tool_scores: Dict[str, int] = {}

    for func in tool_callables:
        name = getattr(func, "__name__", str(func))
        score = 2 if name in CORE_TOOLS else 0
        
        # Check name tokens
        name_tokens = name.split("_")
        for token in query_tokens:
            if token in name_tokens:
                score += 5
            elif token in name:
                score += 2

        # Check tag matches
        tags = TOOL_TAGS.get(name, [])
        for tag in tags:
            if tag in query_tokens:
                score += 4
            elif any(token.startswith(tag) or tag.startswith(token) for token in query_tokens if len(token) > 3):
                score += 2

        tool_scores[name] = score

    # Sort tools by descending relevance score
    sorted_names = sorted(tool_scores.keys(), key=lambda k: tool_scores[k], reverse=True)
    selected_names = set(sorted_names[:max_tools])

    # Return matching callable list preserving rank
    selected_callables = [f for f in tool_callables if getattr(f, "__name__", "") in selected_names]
    return selected_callables[:max_tools]


def validate_tool_arguments(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validates tool arguments against the expected schema before execution.
    Returns (True, None) on success, or (False, error_reason) on failure.
    """
    if tool_name not in TOOL_REGISTRY:
        return False, f"Unknown tool '{tool_name}'."

    func = TOOL_REGISTRY[tool_name]
    schema = func_to_schema(func)
    parameters = schema.get("function", {}).get("parameters", {})
    required = parameters.get("required", [])
    properties = parameters.get("properties", {})

    # 1. Verify all required properties exist
    for req in required:
        if req not in args:
            return False, f"Missing required parameter '{req}' for tool '{tool_name}'."
        if args[req] is None:
            return False, f"Required parameter '{req}' cannot be null for tool '{tool_name}'."

    # 2. Verify types
    for key, val in args.items():
        if key in properties:
            expected_type = properties[key].get("type")
            if expected_type == "string" and not isinstance(val, str):
                return False, f"Parameter '{key}' must be string, got {type(val).__name__}."
            elif expected_type == "integer":
                if isinstance(val, bool):
                    return False, f"Parameter '{key}' must be integer, got boolean."
                if not isinstance(val, int):
                    if isinstance(val, str) and (val.isdigit() or (val.startswith("-") and val[1:].isdigit())):
                        continue
                    if isinstance(val, float) and val.is_integer():
                        continue
                    return False, f"Parameter '{key}' must be integer, got {type(val).__name__}."
            elif expected_type == "number":
                if isinstance(val, bool):
                    return False, f"Parameter '{key}' must be number, got boolean."
                if not isinstance(val, (int, float)):
                    return False, f"Parameter '{key}' must be number, got {type(val).__name__}."
            elif expected_type == "boolean":
                if not isinstance(val, bool):
                    if isinstance(val, str) and val.lower() in ("true", "false", "1", "0"):
                        continue
                    return False, f"Parameter '{key}' must be boolean, got {type(val).__name__}."
            elif expected_type == "array" and not isinstance(val, (list, tuple)):
                return False, f"Parameter '{key}' must be a list/array, got {type(val).__name__}."
            elif expected_type == "object" and not isinstance(val, dict):
                return False, f"Parameter '{key}' must be a dict/object, got {type(val).__name__}."

    return True, None
