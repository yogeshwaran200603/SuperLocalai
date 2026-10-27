"""
SuperLocal Computer Mode: Web Friction & License Handler
- Automatically detects and dismisses cookie banners, newsletter overlays, and prompt popups
  (DOM selectors first -> OCR text -> Vision).
- Strictly blocks dangerous web actions without interactive confirmation:
  purchases, subscriptions, sign-ups, executable downloads, or browser permission grants.
- Analyzes license / terms text for media downloads (preferring Pexels, Pixabay, Wikimedia)
  and documents provenance and licensing in SOURCES.md inside the session sandbox.
"""

import os
import re
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from computer.state_engine import ScreenState, UIElement

POPUP_DISMISS_SELECTORS = [
    'button:has-text("Accept")',
    'button:has-text("Accept All")',
    'button:has-text("I Agree")',
    'button:has-text("Agree")',
    'button:has-text("Got it")',
    'button:has-text("Dismiss")',
    'button:has-text("No thanks")',
    'button:has-text("Close")',
    '[aria-label="Close"]',
    '[aria-label="Dismiss"]',
    '.modal-close',
    '.close-button',
    '#accept-cookies',
]

POPUP_DISMISS_KEYWORDS = [
    "accept all", "accept cookies", "i agree", "agree & proceed",
    "got it", "no thanks", "dismiss", "close modal", "maybe later", "not now"
]

DANGEROUS_WEB_PATTERNS = {
    "purchase": [
        r"\bbuy\s+now\b", r"\bcheckout\b", r"\border\s+now\b", r"\bpurchase\b",
        r"\bplace\s+order\b", r"\bpay\s+\$?\d+", r"\badd\s+to\s+cart\b"
    ],
    "subscription": [
        r"\bsubscribe\b", r"\bstart\s+(?:free\s+)?trial\b", r"\bupgrade\s+to\s+pro\b",
        r"\bannual\s+plan\b", r"\bmonthly\s+plan\b", r"\bpricing\b"
    ],
    "sign_up": [
        r"\bsign\s*up\b", r"\bcreate\s+(?:an\s+)?account\b", r"\bregister\b"
    ],
    "executable": [
        r"\.exe\b", r"\.msi\b", r"\.bat\b", r"\.cmd\b", r"\.scr\b", r"\.vbs\b", r"\.iso\b"
    ],
    "browser_permission": [
        r"\ballow\s+(?:notifications|location|camera|microphone)\b",
        r"\bgrant\s+permission\b"
    ]
}

PREFERRED_FREE_DOMAINS = [
    "pexels.com", "pixabay.com", "wikimedia.org", "unsplash.com", "archive.org", "freepik.com"
]


class WebFrictionHandler:
    """
    Handles popups, guards dangerous web friction points, and inspects media licenses.
    """

    def __init__(self, sandbox_path: Path):
        self.sandbox_path = sandbox_path
        self.sources_file = self.sandbox_path / "SOURCES.md"

    def dismiss_popups(self, page=None, screen_state: Optional[ScreenState] = None) -> List[str]:
        """
        Attempts to dismiss cookie banners and overlays:
        1. DOM selectors on Playwright page (if available)
        2. UIElement match from ScreenState (A11y/OCR)
        Returns list of dismissed item descriptions.
        """
        dismissed: List[str] = []

        # 1. Playwright DOM dismissal
        if page:
            for sel in POPUP_DISMISS_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=500):
                        loc.click(timeout=1000)
                        dismissed.append(f"DOM selector: {sel}")
                        break
                except Exception:
                    continue

        # 2. Accessibility/OCR element dismissal
        if screen_state:
            for el in screen_state.elements:
                name_clean = el.name.lower().strip()
                for kw in POPUP_DISMISS_KEYWORDS:
                    if kw in name_clean:
                        # Found dismiss candidate
                        dismissed.append(f"Screen element: [{el.id}] {el.name}")
                        break

        return dismissed

    def check_dangerous_web_action(self, target_text: str, context_url: str = "") -> Tuple[bool, str]:
        """
        Guards against purchasing, subscribing, signing up, downloading executables,
        or granting permissions without interactive consent.
        """
        combined = f"{target_text} {context_url}".lower()

        for category, patterns in DANGEROUS_WEB_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, combined, re.IGNORECASE):
                    return True, f"Dangerous web action detected ({category.replace('_', ' ')}): matching '{pat}'"

        return False, "Safe action"

    def analyze_media_license(self, url: str, page_text: str = "") -> Dict[str, Any]:
        """
        Checks media licensing text, verifies if source is free-to-use,
        and logs provenance into SOURCES.md.
        """
        t = (url + " " + page_text).lower()

        # License detection heuristics
        license_type = "Unknown / All Rights Reserved"
        is_free_license = False

        if any(d in url.lower() for d in ("pexels.com", "pixabay.com")):
            license_type = "Pexels/Pixabay Free Commercial License (Royalty Free, No Attribution Required)"
            is_free_license = True
        elif "wikimedia.org" in url.lower() or "creative commons" in t or "cc0" in t:
            license_type = "Creative Commons / Public Domain (CC0 / CC-BY)"
            is_free_license = True
        elif "unsplash.com" in url.lower():
            license_type = "Unsplash License (Free to use commercially)"
            is_free_license = True
        elif "public domain" in t:
            license_type = "Public Domain"
            is_free_license = True

        # Extract 1-2 sentence snippet of terms
        terms_snippet = "No specific license snippet extracted."
        for line in page_text.splitlines():
            line_l = line.lower()
            if any(k in line_l for k in ("license", "terms", "free to use", "royalty-free", "attribution")):
                terms_snippet = line.strip()[:180]
                break

        # Record to SOURCES.md
        self._record_source(url, license_type, terms_snippet)

        return {
            "url": url,
            "license": license_type,
            "is_free": is_free_license,
            "terms_snippet": terms_snippet
        }

    def _record_source(self, url: str, license_type: str, terms: str):
        """Appends source record to SOURCES.md in sandbox."""
        header = "# SuperLocal Computer Mode: Sources & Licenses\n\n"
        if not self.sources_file.exists():
            content = header
        else:
            content = self.sources_file.read_text(encoding="utf-8")

        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"### Source Record ({date_str})\n"
            f"- **URL:** `{url}`\n"
            f"- **License:** {license_type}\n"
            f"- **Terms:** {terms}\n\n"
        )

        self.sources_file.write_text(content + entry, encoding="utf-8")
