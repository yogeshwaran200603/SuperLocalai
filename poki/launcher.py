"""
SuperLocal Poki Player: Game Launcher & Playwright Controller
- Navigates to Poki game URL using Playwright with persistent context
- Validates single-player status on page tags, title, and description
- Handles cookie banners, "click to play" splash buttons, and ad breaks
- Computes game canvas bounding box on screen for fast capture
- Controls only the game tab, leaving other tabs untouched
"""

import re
import time
from typing import Dict, Any, Tuple, Optional
from rich.console import Console

from tools.browser import get_browser_page
from poki.guards import check_single_player_or_refuse, print_poki_terms_notice_once

console = Console()

COOKIE_DISMISS_SELECTORS = [
    'button:has-text("Accept")',
    'button:has-text("Accept All")',
    'button:has-text("I Agree")',
    '#accept-cookies',
    '.qc-cmp2-summary-buttons button[mode="primary"]',
]

PLAY_SPLASH_SELECTORS = [
    'button:has-text("Play")',
    'button:has-text("Click to play")',
    '#play-button',
    '.play-button',
    '[data-testid="play-button"]'
]


def normalize_poki_url(game_query: str) -> str:
    """Converts a game name or slug into a full Poki game URL."""
    q = game_query.strip()
    if q.startswith("http://") or q.startswith("https://"):
        return q

    # Clean slug
    slug = q.lower().replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return f"https://poki.com/en/g/{slug}"


class PokiGameLauncher:
    """
    Manages Playwright lifecycle, game navigation, ad handling, and canvas locating.
    """

    def __init__(self):
        self.current_page = None
        self.game_url = ""
        self.canvas_bounds = (0, 0, 800, 600)

    def launch_game(self, game_query: str) -> Tuple[bool, str, Optional[Any]]:
        """
        Launches the game page, validates single-player rules, dismisses popups,
        and locates the game canvas.
        Returns: (success: bool, message: str, page_object)
        """
        print_poki_terms_notice_once()

        self.game_url = normalize_poki_url(game_query)
        console.print(f"[dim]Navigating to Poki game: {self.game_url}...[/dim]")

        try:
            page = get_browser_page()
            self.current_page = page
            page.goto(self.game_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(1.0)
        except Exception as e:
            return False, f"Failed to load game URL {self.game_url}: {e}", None

        # 1. Single-player Verification
        try:
            title = page.title()
            body_text = page.inner_text("body", timeout=3000)[:2000]
            # Extract tags/categories if present
            tags = []
            try:
                tag_elems = page.locator('a[href*="/category/"], a[href*="/tags/"]').all()
                tags = [t.inner_text() for t in tag_elems[:10]]
            except Exception:
                pass

            is_sp, sp_msg = check_single_player_or_refuse(
                page_text=f"{title} {body_text}",
                tags=tags,
                game_url=self.game_url
            )
            if not is_sp:
                return False, sp_msg, None
        except Exception as e:
            console.print(f"[dim]Guard check notice: {e}[/dim]")

        # 2. Dismiss Cookie Banners
        self.dismiss_cookie_banners(page)

        # 3. Handle Ad break and Play overlays
        self.handle_ad_break_and_splash(page)

        # 4. Find Canvas Bounding Box
        bounds = self.detect_game_canvas_bounds(page)
        if bounds:
            self.canvas_bounds = bounds
            console.print(f"[dim]Located game canvas bounding box: {bounds}[/dim]")

        return True, "Game successfully launched and ready.", page

    def dismiss_cookie_banners(self, page):
        """Attempts to click cookie consent accept buttons."""
        for sel in COOKIE_DISMISS_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    loc.click(timeout=1000)
                    time.sleep(0.5)
                    break
            except Exception:
                continue

    def handle_ad_break_and_splash(self, page):
        """Waits for initial ad break to clear and clicks 'Play' splash button."""
        console.print("[dim]Waiting for game canvas to become interactive...[/dim]")

        # Check for splash button
        for sel in PLAY_SPLASH_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=1500)
                    time.sleep(1.0)
                    break
            except Exception:
                continue

        # Wait up to 10 seconds for ad container to hide or canvas to appear
        t_start = time.time()
        while time.time() - t_start < 10.0:
            try:
                # Check if canvas exists and has non-zero size
                canvas = page.locator("canvas").first
                if canvas.count() > 0:
                    box = canvas.bounding_box()
                    if box and box["width"] > 100 and box["height"] > 100:
                        break
            except Exception:
                pass
            time.sleep(0.5)

    def detect_game_canvas_bounds(self, page) -> Optional[Tuple[int, int, int, int]]:
        """
        Determines screen coordinates (x, y, w, h) for the game canvas or iframe.
        """
        if not page:
            return None

        try:
            # 1. Try canvas inside main page
            canvas = page.locator("canvas").first
            if canvas.count() > 0:
                box = canvas.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50:
                    return (int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]))

            # 2. Try iframe#game-player
            iframe = page.locator("iframe#game-player, iframe").first
            if iframe.count() > 0:
                box = iframe.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50:
                    return (int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]))
        except Exception:
            pass

        return None
