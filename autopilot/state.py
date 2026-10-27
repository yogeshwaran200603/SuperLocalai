"""
SuperLocal Autopilot: State Machine and SQLite Persistence Store
Manages job lifecycles, step tracking, checkpoints, and database synchronization.
"""

import os
import json
import time
import sqlite3
import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from config import DB_PATH, JOBS_DIR


class JobStatus:
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    DRY_RUN = "dry_run"


class StepStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class JobStep:
    id: int
    description: str
    tool: str
    args: Dict[str, Any] = field(default_factory=dict)
    success_check: Any = "exit_code_zero"
    risk_level: str = "low"  # low, medium, high
    permission_level: str = "workspace_write"  # read_only, workspace_write, system
    dependencies: List[int] = field(default_factory=list)
    status: str = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    git_commit: Optional[str] = None
    retry_count: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobStep":
        valid_keys = {f for f in cls.__annotations__}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class JobState:
    id: str
    goal: str
    category: str
    workspace_dir: str
    status: str = JobStatus.PENDING
    steps: List[JobStep] = field(default_factory=list)
    current_step_id: int = 0
    model_calls: int = 0
    desktop_actions: int = 0
    start_time: float = field(default_factory=time.time)
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    report_markdown: str = ""

    def get_step(self, step_id: int) -> Optional[JobStep]:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def format_elapsed(self) -> str:
        sec = int(self.elapsed_seconds())
        mins = sec // 60
        s = sec % 60
        return f"{mins:02d}:{s:02d}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


class AutopilotStateStore:
    """
    Persists Autopilot jobs and steps to the central SQLite database.
    Allows resuming after interruptions and inspecting past jobs.
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_tables(self):
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_jobs (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    category TEXT NOT NULL,
                    workspace_dir TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step_id INTEGER DEFAULT 0,
                    total_steps INTEGER DEFAULT 0,
                    model_calls INTEGER DEFAULT 0,
                    desktop_actions INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    report_markdown TEXT,
                    plan_json TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS autopilot_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    step_id INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    args_json TEXT,
                    success_check TEXT,
                    risk_level TEXT,
                    permission_level TEXT,
                    dependencies_json TEXT,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    git_commit TEXT,
                    retry_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES autopilot_jobs(id) ON DELETE CASCADE
                )
            """)

    def save_job(self, job: JobState):
        """Inserts or updates job record and all steps."""
        job.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        plan_json = json.dumps([s.to_dict() for s in job.steps])

        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO autopilot_jobs (
                    id, goal, category, workspace_dir, status,
                    current_step_id, total_steps, model_calls,
                    desktop_actions, created_at, updated_at,
                    report_markdown, plan_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    current_step_id=excluded.current_step_id,
                    total_steps=excluded.total_steps,
                    model_calls=excluded.model_calls,
                    desktop_actions=excluded.desktop_actions,
                    updated_at=excluded.updated_at,
                    report_markdown=excluded.report_markdown,
                    plan_json=excluded.plan_json
            """, (
                job.id, job.goal, job.category, job.workspace_dir, job.status,
                job.current_step_id, len(job.steps), job.model_calls,
                job.desktop_actions, job.created_at, job.updated_at,
                job.report_markdown, plan_json
            ))

            for s in job.steps:
                cur.execute("""
                    INSERT INTO autopilot_steps (
                        job_id, step_id, description, tool, args_json,
                        success_check, risk_level, permission_level,
                        dependencies_json, status, result_json,
                        git_commit, retry_count, started_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status=excluded.status,
                        result_json=excluded.result_json,
                        git_commit=excluded.git_commit,
                        retry_count=excluded.retry_count,
                        completed_at=excluded.completed_at
                """, (
                    job.id, s.id, s.description, s.tool, json.dumps(s.args),
                    json.dumps(s.success_check) if not isinstance(s.success_check, str) else s.success_check,
                    s.risk_level, s.permission_level, json.dumps(s.dependencies),
                    s.status, json.dumps(s.result) if s.result else None,
                    s.git_commit, s.retry_count, s.started_at, s.completed_at
                ))

    def get_job(self, job_id: str) -> Optional[JobState]:
        """Retrieves job state and reconstructs steps."""
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM autopilot_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None

            steps_data = []
            if row["plan_json"]:
                try:
                    steps_data = json.loads(row["plan_json"])
                except Exception:
                    pass

            steps = [JobStep.from_dict(sd) for sd in steps_data]

            job = JobState(
                id=row["id"],
                goal=row["goal"],
                category=row["category"],
                workspace_dir=row["workspace_dir"],
                status=row["status"],
                steps=steps,
                current_step_id=row["current_step_id"],
                model_calls=row["model_calls"],
                desktop_actions=row["desktop_actions"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                report_markdown=row["report_markdown"] or "",
            )
            return job

    def list_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists past autopilot jobs."""
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, goal, category, workspace_dir, status,
                       current_step_id, total_steps, created_at, updated_at
                FROM autopilot_jobs
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_latest_active_job(self) -> Optional[JobState]:
        """Finds any currently running or paused job, falling back to most recent job."""
        with self._connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM autopilot_jobs
                WHERE status IN ('running', 'paused', 'planning')
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                cur.execute("""
                    SELECT id FROM autopilot_jobs
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
            if row:
                return self.get_job(row["id"])
            return None
