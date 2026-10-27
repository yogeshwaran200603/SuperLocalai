"""
SuperLocal Voice Assistant: Wake Word Detection Module
Supports 'hey superlocal', 'hey astra', custom wake words, Push-To-Talk (F9),
and openwakeword offline model integration with acoustic/text fallback.
"""

import re
import os
from typing import List, Tuple, Optional
import numpy as np

try:
    import keyboard
except ImportError:
    keyboard = None

from config import WAKE_WORDS, CUSTOM_WAKE_WORD, VOICE_PTT_KEY


class WakeWordDetector:
    """
    Handles wake word detection and Push-to-Talk (PTT) overrides for SuperLocal.
    """
    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        ptt_key: Optional[str] = None,
        use_openwakeword: bool = True,
    ):
        raw_words = wake_words or WAKE_WORDS
        self.wake_words = [w.strip().lower() for w in raw_words if w.strip()]
        if CUSTOM_WAKE_WORD and CUSTOM_WAKE_WORD not in self.wake_words:
            self.wake_words.insert(0, CUSTOM_WAKE_WORD)
        
        self.ptt_key = (ptt_key or VOICE_PTT_KEY).lower()
        self.oww_model = None
        
        if use_openwakeword:
            try:
                from openwakeword.model import Model
                # Attempt to initialize if models exist
                self.oww_model = Model(inference_framework="onnx")
            except Exception:
                self.oww_model = None

    def is_ptt_active(self) -> bool:
        """Checks if the configured Push-To-Talk key (e.g. F9) is currently held down."""
        if not keyboard or not self.ptt_key:
            return False
        try:
            return keyboard.is_pressed(self.ptt_key)
        except Exception:
            return False

    def detect_in_text(self, transcript: str) -> Tuple[bool, str]:
        """
        Checks if a transcript begins with or prominently includes one of the configured wake words.
        Returns (matched: bool, cleaned_command: str).
        """
        if not transcript:
            return False, ""

        clean_text = transcript.strip()
        text_lower = clean_text.lower()

        # Sort wake words by length descending so longer phrases match first ("hey superlocal" before "superlocal")
        sorted_wake = sorted(self.wake_words, key=len, reverse=True)

        for w in sorted_wake:
            pattern = r"^\s*" + re.escape(w) + r"[\s,\.!\?:]*(.*)$"
            m = re.match(pattern, text_lower, re.IGNORECASE)
            if m:
                # Calculate start of command in original casing
                matched_len = len(clean_text) - len(m.group(1))
                command = clean_text[matched_len:].strip()
                # Strip leading punctuation left over
                command = re.sub(r"^[\s,\.!\?:]+", "", command).strip()
                return True, command

        # Also check if wake word appears at start with minor filler (e.g. "uh hey superlocal ...")
        for w in sorted_wake:
            filler_pattern = r"^(?:uh|um|okay|ok|yo|hi|hello)\s+" + re.escape(w) + r"[\s,\.!\?:]*(.*)$"
            m = re.match(filler_pattern, text_lower, re.IGNORECASE)
            if m:
                matched_len = len(clean_text) - len(m.group(1))
                command = clean_text[matched_len:].strip()
                command = re.sub(r"^[\s,\.!\?:]+", "", command).strip()
                return True, command

        return False, clean_text

    def process_utterance(
        self,
        transcript: str,
        audio_chunk: Optional[np.ndarray] = None,
        ptt_triggered: bool = False,
        wake_word_required: bool = True,
    ) -> Tuple[bool, str]:
        """
        Determines whether the utterance is authorized to proceed to the agent loop.
        If PTT was pressed or wake_word_required is False, always accepts.
        Otherwise requires a recognized wake word.
        """
        if ptt_triggered:
            return True, transcript.strip()

        if not wake_word_required:
            return True, transcript.strip()

        matched, command = self.detect_in_text(transcript)
        return matched, command
