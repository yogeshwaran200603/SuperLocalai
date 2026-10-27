"""
SuperLocal Voice Assistant: Voice Activity Detection (VAD) Module
Uses webrtcvad with an energy-based gate and speech duration filtering.
Ensures no empty clips or sub-second noise blips trigger speech-to-text.
"""

import collections
import numpy as np
from typing import List, Optional, Tuple

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

from config import (
    MIN_RMS,
    MIN_SPEECH_DURATION,
    TRAILING_SILENCE,
    VAD_THRESHOLD,
)


class VADProcessor:
    """
    Processes 16kHz audio stream, detects speech onset and trailing silence,
    and enforces minimum speech duration (>=0.6s) and RMS thresholds.
    """
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        vad_mode: int = 2,
        silence_timeout_sec: float = TRAILING_SILENCE,
        min_speech_duration_sec: float = MIN_SPEECH_DURATION,
        max_utterance_sec: float = 15.0,
        energy_threshold: float = MIN_RMS,
        vad_threshold: float = VAD_THRESHOLD,
    ):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = int(sample_rate * frame_duration_ms / 1000)
        self.frame_bytes = self.frame_samples * 2  # 16-bit PCM = 2 bytes per sample

        self.vad = None
        if webrtcvad:
            try:
                self.vad = webrtcvad.Vad(vad_mode)
            except Exception:
                self.vad = None

        self.silence_timeout_sec = silence_timeout_sec
        self.min_speech_duration_sec = min_speech_duration_sec
        self.max_utterance_sec = max_utterance_sec
        self.energy_threshold = energy_threshold
        self.vad_threshold = vad_threshold

        # Frame limits
        self.silence_limit_frames = int(silence_timeout_sec * 1000 / frame_duration_ms)
        self.min_speech_frames = int(min_speech_duration_sec * 1000 / frame_duration_ms)
        self.max_utterance_frames = int(max_utterance_sec * 1000 / frame_duration_ms)
        self.ring_buffer_size = int(300 / frame_duration_ms)  # 300ms pre-speech buffer

        self.reset()

    def reset(self):
        """Resets the state for a new utterance."""
        self.is_speech_active = False
        self.silence_frames_count = 0
        self.total_speech_frames = 0
        self.active_speech_frames = 0
        self.pre_speech_buffer = collections.deque(maxlen=self.ring_buffer_size)
        self.accumulated_frames: List[bytes] = []

    def compute_rms(self, pcm_bytes: bytes) -> float:
        """Calculates RMS energy of 16-bit PCM bytes."""
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if len(samples) == 0:
                return 0.0
            return float(np.sqrt(np.mean(samples ** 2)))
        except Exception:
            return 0.0

    def is_speech_frame(self, pcm_bytes: bytes) -> bool:
        """
        Determines if a single audio frame contains voice activity.
        Combines RMS energy threshold with WebRTC VAD classification.
        """
        rms = self.compute_rms(pcm_bytes)
        if rms < self.energy_threshold:
            return False

        if len(pcm_bytes) != self.frame_bytes:
            return True

        if self.vad:
            try:
                return self.vad.is_speech(pcm_bytes, self.sample_rate)
            except Exception:
                pass

        return True

    def get_current_buffer(self) -> bytes:
        """Returns the currently accumulated audio buffer for partial live transcription."""
        if not self.accumulated_frames:
            return b""
        return b"".join(self.accumulated_frames)

    def process_frame(self, frame_pcm: bytes) -> Tuple[bool, Optional[bytes]]:
        """
        Processes a single 30ms frame.
        Returns:
            (is_active_speech: bool, completed_utterance_bytes: Optional[bytes])
        Only returns completed_utterance_bytes when:
            - Speech duration >= min_speech_duration_sec (0.6s)
            - Overall utterance RMS >= energy_threshold
            - Trailing silence >= silence_timeout_sec (0.8s)
        Sub-second noise blips or silence are silently discarded without returning an utterance.
        """
        speech = self.is_speech_frame(frame_pcm)

        if not self.is_speech_active:
            if speech:
                # Speech onset
                self.is_speech_active = True
                self.silence_frames_count = 0
                self.accumulated_frames = list(self.pre_speech_buffer)
                self.accumulated_frames.append(frame_pcm)
                self.total_speech_frames = 1
                self.active_speech_frames = 1
                return True, None
            else:
                self.pre_speech_buffer.append(frame_pcm)
                return False, None
        else:
            # Inside an active utterance
            self.accumulated_frames.append(frame_pcm)
            self.total_speech_frames += 1

            if speech:
                self.active_speech_frames += 1
                self.silence_frames_count = 0
            else:
                self.silence_frames_count += 1

            reached_silence = self.silence_frames_count >= self.silence_limit_frames
            reached_max = self.total_speech_frames >= self.max_utterance_frames

            if reached_silence or reached_max:
                complete_audio = b"".join(self.accumulated_frames)
                speech_count = self.active_speech_frames
                self.reset()

                # Filter out empty / sub-second noise clips
                if speech_count < self.min_speech_frames:
                    # Clip had less than 0.6s of actual speech -> discard silently
                    return False, None

                # Verify overall audio energy
                avg_rms = self.compute_rms(complete_audio)
                if avg_rms < self.energy_threshold:
                    # Audio energy was too low -> discard silently
                    return False, None

                return False, complete_audio

            return True, None
