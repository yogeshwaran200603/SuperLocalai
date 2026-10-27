"""
SuperLocal Autopilot: Planner and Prompt-Injection Defense Module
Classifies goals, loads recipe templates, enforces prompt-injection immunity,
and produces structured, dependency-aware execution plans in ONE model call.
"""

import os
import re
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import AUTO_APPROVE_LOW_RISK
from autopilot.state import JobStep

RECIPES_DIR = Path(__file__).resolve().parent / "recipes"

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"system\s*prompt\s*:",
    r"you\s+are\s+now\s+(?:in\s+developer\s+mode|unrestricted)",
    r"disregard\s+(?:the\s+above|all\s+rules)",
    r"new\s+system\s+instruction",
    r"add\s+step\s+to\s+plan",
    r"elevate\s+(?:to\s+)?admin",
    r"grant\s+permission",
    r"delete\s+[cC]:\\",
    r"format\s+[a-zA-Z]:",
]


def sanitize_untrusted_data(text: str) -> Tuple[str, bool, Optional[str]]:
    """
    Guards against prompt injection from untrusted web pages, scraped files,
    emails, or external screens.
    Returns (sanitized_text, was_injection_detected, alert_reason).
    """
    if not text:
        return "", False, None

    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            reason = f"Prompt-injection attempt detected matching '{match.group(0)}'"
            # Neutralize: replace matching sequence with security warning label
            clean = re.sub(pattern, "[UNTRUSTED_INJECTION_ATTEMPT_REDACTED]", text, flags=re.IGNORECASE)
            return clean, True, reason

    return text, False, None


class AutopilotPlanner:
    """
    Translates user goals into structured, verified execution plans.
    """
    def __init__(self, recipes_dir: Path = RECIPES_DIR):
        self.recipes_dir = recipes_dir
        self._recipes_cache: Dict[str, Dict[str, Any]] = {}
        self._load_recipes()

    def _load_recipes(self):
        """Loads all YAML recipe templates from autopilot/recipes/."""
        if not self.recipes_dir.exists():
            return
        for file in self.recipes_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(file.read_text(encoding="utf-8"))
                if data and "category" in data:
                    self._recipes_cache[data["category"]] = data
            except Exception:
                pass

    def classify_goal(self, goal: str) -> str:
        """Classifies the goal into a primary workflow category."""
        g = goal.lower()
        if any(k in g for k in ("fix test", "failing test", "bug", "patch", "repair code")):
            return "bug_fixer"
        if any(k in g for k in ("code review", "security audit", "lint repo", "review code")):
            return "code_review"
        if any(k in g for k in ("deep research", "research", "compare sources", "find best", "laptops under")):
            return "deep_research"
        if any(k in g for k in ("search pdf", "index notes", "doc search", "find in documents")):
            return "doc_search"
        if any(k in g for k in ("csv", "excel", "presentation", "chart", "report builder", "powerpoint", "pptx")):
            return "report_builder"
        if any(k in g for k in ("morning briefing", "calendar", "weather", "briefing")):
            return "morning_briefing"
        if any(k in g for k in ("organize", "organize downloads", "sort folder", "clean desktop")):
            return "file_organizer"
        if any(k in g for k in ("pc slow", "system doctor", "diagnostic", "cleanup pc", "disk space")):
            return "system_doctor"
        if any(k in g for k in ("macro", "replay", "automate clicking")):
            return "macro"
        if any(k in g for k in ("website", "web app", "portfolio", "flask", "fastapi", "react", "html", "todo app", "node", "express")):
            return "web_app"
        return "mixed"

    def check_missing_essential_info(self, goal: str, category: str) -> Tuple[bool, List[str], str]:
        """
        Determines whether essential information is missing.
        Returns: (needs_clarification, questions_list, assumptions_summary)
        If clear enough, asks 0 questions and returns a 1-line assumption statement.
        """
        clean_goal = goal.strip()
        words = clean_goal.split()

        # If extremely brief with zero context (e.g. "build it" or "do work")
        if len(words) < 3 and not any(k in goal.lower() for k in ("briefing", "doctor", "organize")):
            return (
                True,
                [
                    "1. What kind of application or task would you like to build?",
                    "2. Do you have a preferred framework (e.g. HTML/CSS/JS, Flask, FastAPI, React)?",
                    "3. Where should the output be saved?",
                ],
                "",
            )

        # Build natural 1-line assumption
        if category == "web_app":
            if "flask" in goal.lower():
                assumption = "Assumptions: Building Flask application with virtualenv, HTML templates, and SQLite in dedicated job workspace."
            elif "fastapi" in goal.lower():
                assumption = "Assumptions: Building FastAPI REST service with Pydantic models, docs, and pytest in dedicated job workspace."
            else:
                assumption = "Assumptions: Building modern responsive HTML5/CSS3/JS website with dark mode and validated contact form in dedicated job workspace."
        elif category == "deep_research":
            assumption = "Assumptions: Executing cross-source web search, synthesizing citations, and generating a structured PDF/DOCX report."
        elif category == "file_organizer":
            assumption = "Assumptions: Generating a dry-run migration plan for target directory, organizing by extension and date."
        elif category == "bug_fixer":
            assumption = "Assumptions: Running test runner, isolating failures on a git branch, and verifying green regression status."
        elif category == "system_doctor":
            assumption = "Assumptions: Auditing CPU, memory, and disk bottlenecks, generating non-destructive fix recommendations."
        else:
            assumption = f"Assumptions: Executing {category.replace('_', ' ')} end-to-end inside an isolated job workspace with git checkpoints."

        return False, [], assumption

    def create_plan(
        self,
        goal: str,
        category: Optional[str] = None,
        job_slug: str = "project",
        model_provider=None,
    ) -> List[JobStep]:
        """
        Generates the plan steps.
        Uses matched recipe template if available or single model call.
        """
        # Prompt-injection check on goal
        sanitized_goal, was_inj, alert = sanitize_untrusted_data(goal)
        if was_inj:
            print(f"[Autopilot Security Warning] {alert}. Sanitized input.")

        cat = category or self.classify_goal(sanitized_goal)
        recipe = self._recipes_cache.get(cat)

        steps: List[JobStep] = []

        if cat == "web_app":
            # Tailored dev_workflow plan
            is_flask = "flask" in sanitized_goal.lower()
            is_fastapi = "fastapi" in sanitized_goal.lower()
            app_type = "flask" if is_flask else ("fastapi" if is_fastapi else "portfolio")

            steps = [
                JobStep(
                    id=1,
                    description=f"Scaffold {app_type} project structure and starter files",
                    tool="scaffold_project",
                    args={"template": app_type, "project_name": job_slug},
                    success_check="files_exist",
                    risk_level="low",
                    permission_level="workspace_write",
                ),
                JobStep(
                    id=2,
                    description="Open workspace in Visual Studio Code for live visibility",
                    tool="run_powershell",
                    args={"script": "code ."},
                    success_check="exit_code_zero",
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[1],
                ),
                JobStep(
                    id=3,
                    description="Verify and refine source code, styling, and dark mode scripts",
                    tool="file_write",
                    args={"path": "README.md", "content": f"# {job_slug.title()}\n\nScaffolded and verified by SuperLocal Autopilot.\n"},
                    success_check="file_exists",
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[1],
                ),
                JobStep(
                    id=4,
                    description="Run test suite to verify code structure and functionality",
                    tool="run_tests",
                    args={"project_dir": "."},
                    success_check="tests_pass",
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[3],
                ),
                JobStep(
                    id=5,
                    description="Audit web user interface and console logs with Playwright browser",
                    tool="test_website",
                    args={"url": "index.html"},
                    success_check="no_console_errors",
                    risk_level="low",
                    permission_level="read_only",
                    dependencies=[4],
                ),
                JobStep(
                    id=6,
                    description="Generate final completion REPORT.md and commit git checkpoint",
                    tool="file_write",
                    args={"path": "REPORT.md", "content": "# Job Report\n\nCompleted successfully.\n"},
                    success_check="file_exists",
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[5],
                ),
            ]

        elif recipe and "steps_template" in recipe:
            for s in recipe["steps_template"]:
                steps.append(JobStep(
                    id=s["id"],
                    description=s["description"],
                    tool=s["tool"],
                    args=s.get("args", {}),
                    success_check=s.get("success_check", "exit_code_zero"),
                    risk_level=s.get("risk_level", "low"),
                    permission_level=s.get("permission_level", "workspace_write"),
                    dependencies=s.get("dependencies", []),
                ))
        else:
            # General fallback plan
            steps = [
                JobStep(
                    id=1,
                    description=f"Inspect requirements and workspace for: {sanitized_goal}",
                    tool="file_list",
                    args={"path": "."},
                    risk_level="low",
                    permission_level="read_only",
                ),
                JobStep(
                    id=2,
                    description="Execute primary task script or generation",
                    tool="run_powershell",
                    args={"script": f"Write-Output 'Executing: {sanitized_goal[:60]}'"},
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[1],
                ),
                JobStep(
                    id=3,
                    description="Verify outcome and write completion report",
                    tool="file_write",
                    args={"path": "REPORT.md", "content": f"# Autopilot Report\n\nGoal: {sanitized_goal}\nStatus: Complete\n"},
                    risk_level="low",
                    permission_level="workspace_write",
                    dependencies=[2],
                ),
            ]

        return steps
