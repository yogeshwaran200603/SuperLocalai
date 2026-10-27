"""
SuperLocal Voice Assistant: Speech-to-Text (STT) Module
Uses faster-whisper with in-memory caching, condition_on_previous_text=False,
vad_filter=True, and strict hallucination filtering.
"""

import re
import numpy as np
from typing import Optional, Tuple, Set
from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
)

_WHISPER_MODEL_INSTANCE = None

# Known Whisper hallucinations on silence / non-speech noise
KNOWN_HALLUCINATIONS: Set[str] = {
    "thank you",
    "thank you.",
    "thank you very much",
    "thank you very much.",
    "thanks for watching",
    "thanks for watching.",
    "you",
    "you.",
    "bye",
    "bye.",
    "subtitles by",
    "subtitles",
    "please subscribe",
    "like and subscribe",
    "transcription by",
    "the end",
    "silence",
    "music",
}


def is_hallucination_or_noise(text: str) -> bool:
    """
    Checks if a transcript is empty, shorter than 2 characters, or a known
    Whisper hallucination / subtitle artifact.
    """
    if not text:
        return True

    clean = text.strip()
    if len(clean) < 2:
        return True

    lower = clean.lower().rstrip(".!,?;:")

    if lower in KNOWN_HALLUCINATIONS:
        return True

    # Check for bracketed audio descriptions like [Music], [Applause], (laughter)
    if re.match(r"^(\[|\().*?(\]|\))$", clean):
        return True

    # Check for subtitle markers
    if any(h in lower for h in ("subtitles by", "transcript by", "thank you for watching")):
        return True

    return False


class SpeechToText:
    """
    Manages in-memory faster-whisper instance, partial streaming transcription,
    and hallucination filtering.
    """
    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        language: Optional[str] = None,
    ):
        self.model_size = model_size or WHISPER_MODEL_SIZE
        self.device = device or WHISPER_DEVICE
        self.compute_type = compute_type or WHISPER_COMPUTE_TYPE
        self.language = language or WHISPER_LANGUAGE
        self._model = None

    @property
    def model(self):
        """Lazily loads and returns the in-memory WhisperModel."""
        if self._model is None:
            self._model = self._get_or_load_model()
        return self._model

    def _get_or_load_model(self):
        """Loads or retrieves the cached WhisperModel singleton in memory."""
        global _WHISPER_MODEL_INSTANCE
        if _WHISPER_MODEL_INSTANCE is not None:
            return _WHISPER_MODEL_INSTANCE

        try:
            from faster_whisper import WhisperModel
            _WHISPER_MODEL_INSTANCE = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            return _WHISPER_MODEL_INSTANCE
        except Exception as e:
            try:
                from faster_whisper import WhisperModel
                _WHISPER_MODEL_INSTANCE = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="float32",
                )
                return _WHISPER_MODEL_INSTANCE
            except Exception as e2:
                print(f"[Voice STT Error] Failed to load WhisperModel: {e2}")
                return None

    def transcribe_partial(
        self,
        pcm_bytes: bytes,
        language: Optional[str] = None,
    ) -> str:
        """
        Fast, low-latency transcription pass (beam_size=1) for live real-time partial updates.
        """
        if not self.model or not pcm_bytes or len(pcm_bytes) < 3200:
            return ""

        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        target_lang = language or self.language

        try:
            segments, _ = self.model.transcribe(
                audio_np,
                beam_size=1,
                language=target_lang,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            parts = [s.text.strip() for s in segments if s.text]
            text = " ".join(parts).strip()
            if is_hallucination_or_noise(text):
                return ""
            return text
        except Exception:
            return ""

    def transcribe_pcm(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        """
        Full transcription pass for completed utterances.
        Uses beam_size=5, condition_on_previous_text=False, and vad_filter=True.
        Returns (transcript, detected_language, probability).
        If transcript is empty, shorter than 2 chars, or a hallucination, returns ("", lang, 0.0).
        """
        if not self.model or not pcm_bytes:
            return "", "en", 0.0

        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        target_lang = language or self.language

        try:
            segments, info = self.model.transcribe(
                audio_np,
                beam_size=5,
                language=target_lang,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            parts = [s.text.strip() for s in segments if s.text]
            transcript = " ".join(parts).strip()

            if is_hallucination_or_noise(transcript):
                return "", info.language, info.language_probability

            return transcript, info.language, info.language_probability
        except Exception as e:
            print(f"[Voice STT Error] Transcription failed: {e}")
            return "", "en", 0.0
