"""
SuperLocal Voice Assistant Package
Provides offline and cloud voice pipelines, wake word detection, VAD, STT, TTS,
safety confirmation gating, and audio device diagnostics.
"""

from voice.wake import WakeWordDetector
from voice.vad import VADProcessor
from voice.stt import SpeechToText, is_hallucination_or_noise
from voice.tts import TextToSpeech, is_tts_speaking, summarize_for_speech
from voice.confirmation import is_dangerous_voice_action, request_voice_confirmation
from voice.audio_retention import save_audio_if_enabled, purge_old_audio_files
from voice.gemini_live import GeminiLiveProvider, GeminiLiveFallbackError
from voice.assistant import (
    VoiceAssistant,
    get_voice_assistant,
    list_audio_devices,
    set_audio_mic,
    show_audio_level,
    voice_test,
)

__all__ = [
    "WakeWordDetector",
    "VADProcessor",
    "SpeechToText",
    "is_hallucination_or_noise",
    "TextToSpeech",
    "is_tts_speaking",
    "summarize_for_speech",
    "is_dangerous_voice_action",
    "request_voice_confirmation",
    "save_audio_if_enabled",
    "purge_old_audio_files",
    "GeminiLiveProvider",
    "GeminiLiveFallbackError",
    "VoiceAssistant",
    "get_voice_assistant",
    "list_audio_devices",
    "set_audio_mic",
    "show_audio_level",
    "voice_test",
]
