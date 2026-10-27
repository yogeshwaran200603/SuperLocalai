"""
Unit Tests for SuperLocal Voice Assistant Mode
Tests empty-clip filter, hallucination filter, live transcript line,
TTS sentence queue and muting cooldown, conversation mode (20s window),
wake word matching, VAD segmentation, and Gemini Live fallback.
All audio input and model calls are mocked.
"""

import time
import queue
import sys
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from voice.wake import WakeWordDetector
from voice.vad import VADProcessor
from voice.stt import SpeechToText, is_hallucination_or_noise
from voice.tts import TextToSpeech, summarize_for_speech, is_tts_speaking, _IS_SPEAKING
from voice.confirmation import is_dangerous_voice_action, request_voice_confirmation
from voice.audio_retention import save_audio_if_enabled, purge_old_audio_files
from voice.gemini_live import GeminiLiveProvider, GeminiLiveFallbackError
from voice.assistant import VoiceAssistant


# ==============================================================================
# 1. Wake Word Logic Tests
# ==============================================================================

def test_wake_word_hey_superlocal():
    detector = WakeWordDetector(wake_words=["hey superlocal", "hey astra", "superlocal"])
    matched, cmd = detector.detect_in_text("Hey SuperLocal, open discord and go to my server")
    assert matched is True
    assert cmd == "open discord and go to my server"


def test_wake_word_alias_hey_astra():
    detector = WakeWordDetector(wake_words=["hey superlocal", "hey astra", "superlocal"])
    matched, cmd = detector.detect_in_text("hey astra what is the battery level?")
    assert matched is True
    assert cmd == "what is the battery level?"


def test_wake_word_short_custom():
    detector = WakeWordDetector(wake_words=["superlocal", "hey superlocal"])
    matched, cmd = detector.detect_in_text("superlocal: open notepad")
    assert matched is True
    assert cmd == "open notepad"


def test_wake_word_rejects_unauthorized_speech():
    detector = WakeWordDetector(wake_words=["hey superlocal", "hey astra"])
    matched, cmd = detector.detect_in_text("turn off the living room lights")
    assert matched is False


def test_push_to_talk_bypasses_wake_word():
    detector = WakeWordDetector(wake_words=["hey superlocal"])
    matched, cmd = detector.process_utterance(
        "open calculator",
        ptt_triggered=True,
        wake_word_required=False,
    )
    assert matched is True
    assert cmd == "open calculator"


# ==============================================================================
# 2. VAD Segmentation & Empty Clip Filtering Tests
# ==============================================================================

def test_vad_silence_frame():
    vad = VADProcessor(sample_rate=16000, frame_duration_ms=30, silence_timeout_sec=0.1)
    silence = b"\x00" * 960
    is_active, utterance = vad.process_frame(silence)
    assert is_active is False
    assert utterance is None


def test_vad_speech_onset_and_trailing_silence_completion():
    vad = VADProcessor(
        sample_rate=16000,
        frame_duration_ms=30,
        silence_timeout_sec=0.06,  # 2 frames of silence triggers completion
        min_speech_duration_sec=0.05,  # 2 frames of speech counts as valid for test
        energy_threshold=0.01,
    )
    speech_frame = (b"\x00\x40\x00\xc0" * 240)  # High RMS > 0.01
    silence_frame = b"\x00" * 960

    # Frame 1: Speech onset
    is_active, comp = vad.process_frame(speech_frame)
    assert is_active is True
    assert comp is None
    assert vad.is_speech_active is True

    # Frame 2: Continuing speech
    is_active, comp = vad.process_frame(speech_frame)
    assert is_active is True
    assert comp is None

    # Frame 3: First trailing silence frame
    is_active, comp = vad.process_frame(silence_frame)
    assert is_active is True
    assert comp is None

    # Frame 4: Second trailing silence frame (silence limit reached -> completes utterance)
    is_active, comp = vad.process_frame(silence_frame)
    assert is_active is False
    assert comp is not None
    assert len(comp) > 0
    assert vad.is_speech_active is False


def test_empty_clip_filter_short_duration():
    """Clips with less than 0.6s of speech must be rejected silently."""
    vad = VADProcessor(
        sample_rate=16000,
        frame_duration_ms=30,
        silence_timeout_sec=0.06,  # 2 frames of silence
        min_speech_duration_sec=0.6,  # Requires at least 20 speech frames
        energy_threshold=0.01,
    )
    speech_frame = (b"\x00\x40\x00\xc0" * 240)
    silence_frame = b"\x00" * 960

    # Only 2 speech frames (0.06s < 0.6s)
    vad.process_frame(speech_frame)
    vad.process_frame(speech_frame)

    # 2 silence frames (triggers end of segment)
    vad.process_frame(silence_frame)
    is_active, comp = vad.process_frame(silence_frame)

    # Must be discarded silently (None returned)
    assert is_active is False
    assert comp is None


def test_empty_clip_filter_low_rms():
    """Clips below MIN_RMS energy must be rejected silently."""
    vad = VADProcessor(
        sample_rate=16000,
        frame_duration_ms=30,
        silence_timeout_sec=0.06,
        min_speech_duration_sec=0.05,
        energy_threshold=0.05,  # High threshold
    )
    # Low energy frame (RMS ~0.01 < 0.05)
    low_speech_frame = (b"\x00\x05\x00\xfa" * 240)
    silence_frame = b"\x00" * 960

    vad.process_frame(low_speech_frame)
    is_active, comp = vad.process_frame(silence_frame)
    assert comp is None


# ==============================================================================
# 3. Whisper Hallucination Filter Tests
# ==============================================================================

def test_hallucination_filter():
    # Known hallucinations must return True (discarded)
    assert is_hallucination_or_noise("") is True
    assert is_hallucination_or_noise("a") is True
    assert is_hallucination_or_noise("thank you") is True
    assert is_hallucination_or_noise("Thank you.") is True
    assert is_hallucination_or_noise("you") is True
    assert is_hallucination_or_noise("bye") is True
    assert is_hallucination_or_noise("thanks for watching") is True
    assert is_hallucination_or_noise("[Music]") is True
    assert is_hallucination_or_noise("(applause)") is True
    assert is_hallucination_or_noise("Subtitles by the Amara.org community") is True

    # Real user commands must return False (accepted)
    assert is_hallucination_or_noise("open discord and go to my server") is False
    assert is_hallucination_or_noise("what is the battery level?") is False
    assert is_hallucination_or_noise("create a folder on Desktop") is False
    assert is_hallucination_or_noise("open notepad") is False


# ==============================================================================
# 4. Confirmation Parsing Tests
# ==============================================================================

def test_is_dangerous_voice_action_detection():
    # Dangerous actions
    assert is_dangerous_voice_action("file_delete", {"path": "important.txt"})[0] is True
    assert is_dangerous_voice_action("whatsapp_send", {"message": "hello"})[0] is True
    assert is_dangerous_voice_action("run_powershell", {"script": "winget install git"})[0] is True
    assert is_dangerous_voice_action("desktop_click", {"target": "delete confirm button"})[0] is True
    assert is_dangerous_voice_action("voice_action", {"command": "pay 100 dollars to store"})[0] is True

    # Safe actions
    assert is_dangerous_voice_action("file_read", {"path": "readme.txt"})[0] is False
    assert is_dangerous_voice_action("data_inspect", {"file_path": "data.csv"})[0] is False
    assert is_dangerous_voice_action("open_app", {"name": "notepad"})[0] is False


def test_voice_confirmation_spoken_yes():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe_pcm.return_value = ("yes, confirm", "en", 0.99)
    mock_record = MagicMock(return_value=b"dummy_pcm")

    confirmed = request_voice_confirmation(
        action_desc="Delete system files",
        tts=mock_tts,
        stt=mock_stt,
        record_func=mock_record,
        timeout_sec=2.0,
    )
    assert confirmed is True
    mock_tts.speak.assert_called_with("Confirmed. Proceeding.")


def test_voice_confirmation_spoken_no():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe_pcm.return_value = ("no, cancel that", "en", 0.98)
    mock_record = MagicMock(return_value=b"dummy_pcm")

    confirmed = request_voice_confirmation(
        action_desc="Delete database",
        tts=mock_tts,
        stt=mock_stt,
        record_func=mock_record,
        timeout_sec=2.0,
    )
    assert confirmed is False
    mock_tts.speak.assert_called_with("Action cancelled.")


def test_voice_confirmation_timeout_cancels():
    mock_tts = MagicMock()
    mock_stt = MagicMock()
    mock_stt.transcribe_pcm.return_value = ("", "en", 0.0)
    mock_record = MagicMock(return_value=b"")

    start = time.time()
    confirmed = request_voice_confirmation(
        action_desc="Format drive D",
        tts=mock_tts,
        stt=mock_stt,
        record_func=mock_record,
        timeout_sec=0.5,
    )
    elapsed = time.time() - start
    assert confirmed is False
    assert elapsed >= 0.4
    mock_tts.speak.assert_called_with("Action cancelled.")


# ==============================================================================
# 5. Text-to-Speech Queue, Summarizer & Muting Cooldown Tests
# ==============================================================================

def test_summarize_for_speech_markdown_cleaning():
    raw = (
        "### Superlocal Summary\n"
        "Completed `open_app`: Launched application 'notepad' locally.\n\n"
        "Here are more details:\n"
        "- PID: 1234\n"
        "- Path: C:\\Windows\\notepad.exe\n"
    )
    spoken = summarize_for_speech(raw)
    assert "###" not in spoken
    assert "`" not in spoken
    assert "Superlocal Summary" not in spoken
    assert "Launched application 'notepad' locally" in spoken


def test_summarize_for_speech_caps_at_two_sentences():
    long_text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    spoken = summarize_for_speech(long_text)
    assert "Sentence one. Sentence two." == spoken


def test_tts_queue_and_muting_cooldown():
    tts = TextToSpeech(engine="pyttsx3")
    tts._play_sentence = MagicMock()

    # Simulate speaking
    tts.speak("Sentence one. Sentence two.")
    assert not tts._speech_queue.empty()

    # Verify stop clears queue and resets speaking
    tts.stop()
    assert tts._speech_queue.empty()


def test_mic_muting_during_speech_and_05s_cooldown():
    import voice.tts as vtts
    # Simulate active speaking
    vtts._IS_SPEAKING.set()
    assert vtts.is_tts_speaking() is True

    # Clear active speaking, verify 0.5s cooldown keeps it muted
    vtts._IS_SPEAKING.clear()
    vtts._LAST_SPEAKING_TIMESTAMP = time.time()  # Just finished
    assert vtts.is_tts_speaking() is True

    # After > 0.5s, muting lifts
    vtts._LAST_SPEAKING_TIMESTAMP = time.time() - 0.6
    assert vtts.is_tts_speaking() is False


# ==============================================================================
# 6. Conversation Mode & Goodbye Command Tests
# ==============================================================================

def test_conversation_mode_20s_window():
    va = VoiceAssistant()
    # Initially inactive
    assert va.in_conversation_mode() is False

    # Simulate reply finishes -> activates 20s conversation window
    va.conversation_until = time.time() + 20.0
    assert va.in_conversation_mode() is True

    # When in conversation mode, wake word is not required
    matched, cmd = va.wake_detector.process_utterance(
        "open calculator",
        ptt_triggered=False,
        wake_word_required=not va.in_conversation_mode(),
    )
    assert matched is True
    assert cmd == "open calculator"

    # Expired conversation window
    va.conversation_until = time.time() - 1.0
    assert va.in_conversation_mode() is False


def test_goodbye_voice_command():
    va = VoiceAssistant()
    va.tts = MagicMock()
    va.is_running = True

    with patch.object(va.stt, "transcribe_pcm", return_value=("goodbye", "en", 0.99)):
        va._process_completed_audio(b"dummy_pcm_audio")
        # Saying goodbye deactivates the voice assistant
        assert va.is_running is False
        va.tts.speak_now.assert_called_with("Goodbye!")


# ==============================================================================
# 7. Live Transcript Line Updating Test
# ==============================================================================

def test_live_transcript_updating():
    va = VoiceAssistant()
    with patch("voice.assistant.Live") as mock_live_cls:
        mock_instance = MagicMock()
        mock_live_cls.return_value = mock_instance

        va._update_live_transcript("open discord")
        assert va._live_display is not None

        va._clear_live_transcript()
        assert va._live_display is None


# ==============================================================================
# 8. Audio Retention Policy Tests
# ==============================================================================

def test_audio_retention_disabled_does_not_save(tmp_path):
    with patch("voice.audio_retention.VOICE_SAVE_AUDIO", False):
        saved = save_audio_if_enabled(b"dummy_pcm_bytes", directory=tmp_path)
        assert saved is None
        assert len(list(tmp_path.glob("*.wav"))) == 0


def test_audio_retention_enabled_saves_and_purges_old_files(tmp_path):
    with patch("voice.audio_retention.VOICE_SAVE_AUDIO", True):
        fresh_path = save_audio_if_enabled(b"\x00" * 3200, directory=tmp_path, prefix="test")
        assert fresh_path is not None
        assert Path(fresh_path).exists()

        old_file = tmp_path / "old_voice_123.wav"
        old_file.write_bytes(b"\x00" * 100)
        old_mtime = time.time() - (26 * 3600)
        import os
        os.utime(str(old_file), (old_mtime, old_mtime))

        purged = purge_old_audio_files(directory=tmp_path, max_age_hours=24.0)
        assert purged >= 1
        assert not old_file.exists()
        assert Path(fresh_path).exists()


# ==============================================================================
# 9. Gemini Live Provider Tests
# ==============================================================================

def test_gemini_live_setup_payload_construction():
    def dummy_tool(query: str, count: int = 5) -> str:
        """Searches documents for query."""
        return query

    provider = GeminiLiveProvider(
        api_key="AIzaSyDummyTestKey",
        model="gemini-2.0-flash-exp",
        tools=[dummy_tool],
    )
    setup = provider.build_setup_message()
    assert "setup" in setup
    assert setup["setup"]["model"] == "models/gemini-2.0-flash-exp"
    assert setup["setup"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    tools_payload = setup["setup"]["tools"][0]["functionDeclarations"]
    assert tools_payload[0]["name"] == "dummy_tool"
    assert "query" in tools_payload[0]["parameters"]["properties"]


@pytest.mark.anyio
async def test_gemini_live_quota_error_triggers_fallback():
    provider = GeminiLiveProvider(api_key="AIzaSyDummyTestKey", model="gemini-2.0-flash-exp")
    with patch("websockets.connect", side_effect=Exception("429 RESOURCE_EXHAUSTED: Rate limit reached")):
        with pytest.raises(GeminiLiveFallbackError) as exc_info:
            await provider.connect()
        assert "quota exhausted (429)" in str(exc_info.value)
