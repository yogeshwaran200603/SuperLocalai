"""
Astra-Local Memory Module
Manages session-level conversational context and persistent SQLite history.
"""

import sqlite3
import json
import uuid
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from config import DB_PATH


class MemoryManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager that ensures transactions commit and connections are closed."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initializes tables for sessions, messages, and tool executions."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls_json TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    args_json TEXT,
                    result_json TEXT,
                    status TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS request_cache (
                    prompt_hash TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_usage (
                    date_str TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    call_count INTEGER DEFAULT 0,
                    PRIMARY KEY (date_str, model_name)
                )
            """)

    def create_session(self, title: str = "New Session") -> str:
        """Creates a new session record and returns its ID."""
        session_id = str(uuid.uuid4())
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (id, title) VALUES (?, ?)",
                (session_id, title)
            )
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None
    ):
        """Appends a message to the session history."""
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO messages (session_id, role, content, tool_calls_json)
                VALUES (?, ?, ?, ?)
            """, (session_id, role, content, tool_calls_json))
            cursor.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,)
            )

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all messages for a given session."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, tool_calls_json FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                msg = {"role": row["role"], "content": row["content"]}
                if row["tool_calls_json"]:
                    msg["tool_calls"] = json.loads(row["tool_calls_json"])
                messages.append(msg)
            return messages

    def record_tool_execution(
        self,
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        status: str = "SUCCESS"
    ):
        """Records tool execution details for audit and recall."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_logs (session_id, tool_name, args_json, result_json, status)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                tool_name,
                json.dumps(args, default=str),
                json.dumps(result, default=str),
                status
            ))

    def list_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists recent sessions."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # =========================================================================
    # Request Cache (10-minute TTL in SQLite)
    # =========================================================================

    def get_cached_response(self, prompt: str) -> Optional[str]:
        """Returns cached response if prompt hash exists and is unexpired."""
        import hashlib, time
        p_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()
        now = time.time()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT response, expires_at FROM request_cache WHERE prompt_hash = ?",
                (p_hash,)
            )
            row = cursor.fetchone()
            if row:
                if row["expires_at"] > now:
                    return row["response"]
                else:
                    cursor.execute("DELETE FROM request_cache WHERE prompt_hash = ?", (p_hash,))
        return None

    def cache_response(self, prompt: str, response: str, ttl_seconds: int = 600):
        """Stores a prompt response in the SQLite cache with TTL."""
        import hashlib, time
        p_hash = hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()
        now = time.time()
        expires = now + ttl_seconds
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO request_cache (prompt_hash, prompt, response, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (p_hash, prompt, response, now, expires))

    # =========================================================================
    # Daily Model Request Tracker (Quota & Rate Tracking)
    # =========================================================================

    def record_api_call(self, model: str, date_str: Optional[str] = None):
        """Increments the daily request counter for the specified model in SQLite."""
        dt = date_str or datetime.date.today().isoformat()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_usage (date_str, model_name, call_count)
                VALUES (?, ?, 1)
                ON CONFLICT(date_str, model_name) DO UPDATE SET call_count = call_count + 1
            """, (dt, model))

    def get_daily_api_calls(self, model: Optional[str] = None, date_str: Optional[str] = None) -> int:
        """Returns total requests today (or for a specific model today)."""
        dt = date_str or datetime.date.today().isoformat()
        with self._connection() as conn:
            cursor = conn.cursor()
            if model:
                cursor.execute(
                    "SELECT call_count FROM daily_usage WHERE date_str = ? AND model_name = ?",
                    (dt, model)
                )
                row = cursor.fetchone()
                return row["call_count"] if row else 0
            else:
                cursor.execute(
                    "SELECT SUM(call_count) as total FROM daily_usage WHERE date_str = ?",
                    (dt,)
                )
                row = cursor.fetchone()
                return int(row["total"] or 0) if row else 0

    def get_daily_usage_summary(self, date_str: Optional[str] = None) -> Dict[str, int]:
        """Returns a mapping of model_name -> call_count for today."""
        dt = date_str or datetime.date.today().isoformat()
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT model_name, call_count FROM daily_usage WHERE date_str = ?",
                (dt,)
            )
            rows = cursor.fetchall()
            return {r["model_name"]: r["call_count"] for r in rows}

    def reset_daily_usage(self, date_str: Optional[str] = None) -> int:
        """Resets daily usage counters in SQLite. Returns number of rows deleted."""
        with self._connection() as conn:
            cursor = conn.cursor()
            if date_str:
                cursor.execute("DELETE FROM daily_usage WHERE date_str = ?", (date_str,))
            else:
                cursor.execute("DELETE FROM daily_usage")
            return cursor.rowcount
