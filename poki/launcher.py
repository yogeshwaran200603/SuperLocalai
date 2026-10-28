"""
SuperLocal Poki Player: Game Launcher & Playwright Controller
- Navigates to Poki game URL using Playwright with persistent context
- Validates single-player status on page tags, title, and description
- Handles cookie banners, "click to play" splash buttons, and ad breaks
- Computes game canvas bounding box on screen for fast capture
- Focuses game canvas with safe click
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
    'button:has-text("Consent")',
    'button:has-text("AGREE")',
    'button:has-text("OK")',
    'button:has-text("Got it")',
    '#accept-cookies',
    '#onetrust-accept-btn-handler',
    '.qc-cmp2-summary-buttons button[mode="primary"]',
    'button[aria-label="Consent"]',
    'button[aria-label="Accept"]',
]

PLAY_SPLASH_SELECTORS = [
    'button:has-text("Play")',
    'button:has-text("Click to play")',
    'button:has-text("PLAY")',
    '#play-button',
    '.play-button',
    '[data-testid="play-button"]',
    'a:has-text("Play")',
    'div[role="button"]:has-text("Play")',
]

CRICKET_ALIASES = [
    "cricket",
    "little master cricket",
    "little master",
    "little-master",
    "little-master-cricket",
]


def normalize_poki_url(game_query: str) -> str:
    """Converts a game name or slug into a full Poki game URL."""
    q = game_query.strip()
    if q.startswith("http://") or q.startswith("https://"):
        return q

    q_lower = q.lower().strip()
    # Direct match for Little Master Cricket
    if any(q_lower == alias or q_lower == alias.replace("-", " ") for alias in CRICKET_ALIASES):
        return "https://poki.com/en/g/little-master-cricket"

    # Clean slug
    slug = q_lower.replace(" ", "-").replace("_", "-")
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
        waits through ad breaks, locates the game canvas, and focuses it.
        Returns: (success: bool, message: str, page_object)
        """
        print_poki_terms_notice_once()

        self.game_url = normalize_poki_url(game_query)
        console.print(f"[dim]Navigating to Poki game: {self.game_url}...[/dim]")

        page = get_browser_page()
        self.current_page = page

        # Navigate with retry logic and longer timeout on failure
        try:
            page.goto(self.game_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            console.print(f"[bold red][Poki Launcher] goto failed: {e}. Retrying once with longer timeout (45s)...[/bold red]")
            try:
                page.goto(self.game_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e2:
                console.print(f"[bold red][Poki Launcher] Retry goto also failed: {e2}. Keeping page open.[/bold red]")
                return False, f"Failed to load game URL {self.game_url}: {e2}", page

        # Wait for game iframe or canvas to appear (timeout 30s)
        try:
            page.wait_for_selector("canvas, iframe#game-player, iframe", timeout=30000)
        except Exception as e:
            console.print(f"[dim]Notice: Canvas/iframe wait selector timeout (proceeding): {e}[/dim]")

        # 1. Single-player Verification
        try:
            title = page.title()
            # Extract game-specific headings and description paragraphs
            headings = [h.inner_text() for h in page.locator("h1, h2, h3").all() if h.inner_text()]
            paragraphs = [p.inner_text() for p in page.locator("p, [class*='description']").all() if p.inner_text()]
            game_text = f"{title} {' '.join(headings)} {' '.join(paragraphs)}"
            if not paragraphs:
                game_text = f"{title} {page.inner_text('body', timeout=2000)[:2000]}"

            # Extract tags/categories scoped to the game section
            tags = []
            try:
                tag_elems = page.locator('.game-info a, #game-tags a, .game-tags a, [data-test="tag"] a, .tags a').all()
                tags = [t.inner_text() for t in tag_elems[:10] if t.inner_text()]
            except Exception:
                pass

            is_sp, sp_msg = check_single_player_or_refuse(
                page_text=game_text,
                tags=tags,
                game_url=self.game_url
            )
            if not is_sp:
                return False, sp_msg, page
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
            # Focus canvas with safe spot click (center of canvas)
            safe_x = bounds[0] + bounds[2] // 2
            safe_y = bounds[1] + bounds[3] // 2
            try:
                page.mouse.click(safe_x, safe_y)
                console.print(f"[dim]Focused game canvas with safe click at ({safe_x}, {safe_y})[/dim]")
            except Exception as e:
                console.print(f"[dim]Safe focus click notice: {e}[/dim]")

        return True, "Game successfully launched and ready.", page

    def dismiss_cookie_banners(self, page):
        """Attempts to click cookie consent accept buttons on main page and frames."""
        for sel in COOKIE_DISMISS_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=500):
                    loc.click(timeout=1000)
                    time.sleep(0.3)
                    break
            except Exception:
                continue

        # Check inside frames
        try:
            for f in page.frames:
                for sel in COOKIE_DISMISS_SELECTORS:
                    try:
                        loc = f.locator(sel).first
                        if loc.is_visible(timeout=300):
                            loc.click(timeout=800)
                            time.sleep(0.3)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    def handle_ad_break_and_splash(self, page):
        """Waits for initial ad break to clear and clicks the game's own 'Play' splash button (never clicking ad frames)."""
        console.print("[dim]Waiting for game canvas to become interactive (ad break safety check)...[/dim]")

        # 1. Check for splash play button on main page
        for sel in PLAY_SPLASH_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=800):
                    loc.click(timeout=1000)
                    time.sleep(0.5)
                    break
            except Exception:
                continue

        # 2. Check game-player iframe specifically (never third-party ad/tracking frames)
        try:
            game_frame = None
            for f in page.frames:
                if f != page.main_frame and ("game-player" in f.name or "game-player" in f.url):
                    game_frame = f
                    break
            if game_frame:
                for sel in PLAY_SPLASH_SELECTORS:
                    try:
                        loc = game_frame.locator(sel).first
                        if loc.is_visible(timeout=500):
                            loc.click(timeout=1000)
                            time.sleep(0.5)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        # 3. Wait up to 15 seconds for ad break to clear and game canvas to become interactive
        t_start = time.time()
        while time.time() - t_start < 15.0:
            try:
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

            # 2. Try iframe#game-player or iframe
            iframe = page.locator("iframe#game-player, iframe").first
            if iframe.count() > 0:
                box = iframe.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50:
                    return (int(box["x"]), int(box["y"]), int(box["width"]), int(box["height"]))
        except Exception:
            pass

        return None
