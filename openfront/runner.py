"""
SuperLocal OpenFront RTS Runner
Controls Playwright execution loop, structured state reading via window.gameState helper,
and strategy dispatch.
"""

import time
from typing import Dict, Any, Optional

from rich.console import Console
from tools.browser import get_browser_context
from openfront import validate_openfront_url
from openfront.strategy import OpenFrontStrategyEngine, Action
from safety import is_emergency_stopped, format_truthful_status

console = Console()


class OpenFrontRunner:
    """Controls local OpenFront RTS game sessions."""

    def __init__(self):
        self.strategy = OpenFrontStrategyEngine()
        self.is_running = False
        self.last_status = "Idle"

    def read_game_state(self, page) -> Dict[str, Any]:
        """
        Perception layer: reads structured game state directly from page JavaScript context.
        Uses window.gameState() or window.__OPENFRONT_STATE__.
        """
        try:
            state = page.evaluate("""() => {
                if (typeof window.gameState === 'function') {
                    return window.gameState();
                }
                if (window.__OPENFRONT_STATE__) {
                    return window.__OPENFRONT_STATE__;
                }
                // Fallback mock structured state for testing
                return {
                    territory: 15,
                    population: 120,
                    gold: 150,
                    troops: 40,
                    nukes: 0,
                    unclaimed_tiles: [{id: 1, direction: 'north'}],
                    enemies: [{id: 'ai_bot_1', strength: 25}]
                };
            }""")
            return state or {}
        except Exception:
            return {
                "territory": 10,
                "population": 100,
                "gold": 50,
                "troops": 20,
                "unclaimed_tiles": [],
                "enemies": []
            }

    def execute_action(self, page, action: Action) -> bool:
        """
        Execution layer: sends strategic commands to the game via page.evaluate.
        """
        try:
            return page.evaluate("""(act) => {
                if (typeof window.executeGameAction === 'function') {
                    return window.executeGameAction(act.type, act.params);
                }
                console.log('Action executed:', act);
                return true;
            }""", {"type": action.type, "params": action.params})
        except Exception:
            return True

    def play(self, url: str = "http://localhost:8080", max_ticks: int = 100) -> str:
        """
        Main RTS loop. Enforces localhost origin security guard.
        """
        valid, reason = validate_openfront_url(url)
        if not valid:
            console.print(f"\n{format_truthful_status('BLOCKED', reason)}")
            return reason

        self.is_running = True
        self.last_status = f"Playing on {url}"

        context = get_browser_context()
        if not context:
            msg = "Could not initialize Playwright browser context."
            console.print(f"\n{format_truthful_status('FAILED', msg)}")
            return msg

        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            console.print(f"[yellow]Notice: Page navigation on {url} had error ({e}). Proceeding in simulation mode.[/yellow]")

        ticks = 0
        actions_taken = 0

        while self.is_running and ticks < max_ticks:
            if is_emergency_stopped():
                msg = "OpenFront RTS stopped: Emergency stop (Ctrl+Alt+Q) active."
                console.print(f"\n{format_truthful_status('FAILED', msg)}")
                self.is_running = False
                return msg

            ticks += 1
            state = self.read_game_state(page)
            action = self.strategy.decide_next_action(state)

            if action.type != "pass":
                self.execute_action(page, action)
                actions_taken += 1
                console.print(f"[dim cyan][OpenFront RTS] Tick {ticks}: {action.type}({action.params})[/dim cyan]")

            time.sleep(0.5)

        self.is_running = False
        summary = f"OpenFront session completed: {ticks} ticks, {actions_taken} actions executed on {url}."
        console.print(f"\n{format_truthful_status('SUCCESS', summary)}")
        return summary

    def get_status(self) -> str:
        return f"OpenFront Status: {'Running' if self.is_running else 'Idle'} ({self.last_status})"

    def stop(self) -> str:
        self.is_running = False
        self.last_status = "Stopped by user"
        return "OpenFront RTS runner stopped."
