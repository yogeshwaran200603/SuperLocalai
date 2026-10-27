"""
SuperLocal Voice Assistant: Text-to-Speech (TTS) Module
Supports Piper neural TTS (if installed) or Windows SAPI5 (pyttsx3).
Features sentence streaming, microphone muting coordination, and fast interruption.
"""

import os
import re
import time
import queue
import shutil
import threading
import subprocess
import tempfile
from typing import Optional, List
from config import (
    TTS_ENGINE,
    PIPER_PATH,
    PIPER_MODEL,
    TTS_VOICE,
    TTS_RATE,
    TTS_VOLUME,
    AUDIO_OUTPUT_DEVICE,
)

_IS_SPEAKING = threading.Event()
_LAST_SPEAKING_TIMESTAMP = 0.0


def is_tts_speaking() -> bool:
    """Returns True if SuperLocal is currently speaking OR within the 0.5s cooldown."""
    global _LAST_SPEAKING_TIMESTAMP
    if _IS_SPEAKING.is_set():
        return True
    return (time.time() - _LAST_SPEAKING_TIMESTAMP) < 0.5


def summarize_for_speech(text: str) -> str:
    """
    Summarizes long markdown, tool results, or multi-turn agent summaries
    into 1-2 concise, conversational spoken sentences.
    """
    if not text:
        return "Done."

    # Remove code blocks, markdown tables, bold/italic markers
    clean = re.sub(r"```[\s\S]*?```", "", text)
    clean = re.sub(r"`.*?`", "", clean)
    clean = re.sub(r"\[.*?\]\(.*?\)", "", clean)
    clean = re.sub(r"[*_#~>]", "", clean)
    clean = re.sub(r"\|.*?\|", "", clean)

    # Normalize whitespace and newlines
    lines = [line.strip() for line in clean.split("\n") if line.strip()]
    if not lines:
        return "Task completed."

    # Filter out header lines like "Superlocal Summary" or "Completed Actions:"
    filtered = []
    for l in lines:
        l_lower = l.lower()
        if any(h in l_lower for h in ("superlocal summary", "completed actions:", "summary:", "tool result")):
            continue
        filtered.append(l)

    text_to_split = " ".join(filtered) if filtered else lines[0]
    # Split into sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text_to_split) if s.strip()]

    if not sentences:
        return "Done."

    # Return at most the first 2 sentences
    spoken = " ".join(sentences[:2])
    # Cap maximum characters for conversational snappiness
    if len(spoken) > 220:
        spoken = sentences[0][:200]
    return spoken


class TextToSpeech:
    """
    Threaded, sentence-streaming TTS engine supporting interruption and microphone muting.
    """
    def __init__(
        self,
        engine: Optional[str] = None,
        piper_path: Optional[str] = None,
        piper_model: Optional[str] = None,
        rate: Optional[int] = None,
        volume: Optional[float] = None,
        voice: Optional[str] = None,
    ):
        self.engine_type = (engine or TTS_ENGINE).lower()
        self.piper_path = piper_path or PIPER_PATH
        self.piper_model = piper_model or PIPER_MODEL
        self.rate = rate or TTS_RATE
        self.volume = volume or TTS_VOLUME
        self.voice = voice or TTS_VOICE

        self._piper_available = self._check_piper()
        self._speech_queue = queue.Queue()
        self._stop_requested = threading.Event()
        self._worker_thread = None
        self._pyttsx3_engine = None

        self._start_worker()

    def _check_piper(self) -> bool:
        """Checks if Piper binary and ONNX model exist and are executable."""
        if self.engine_type in ("pyttsx3", "windows"):
            return False
        if self.piper_path and os.path.isfile(self.piper_path):
            if self.piper_model and os.path.isfile(self.piper_model):
                return True
        # Check if piper command is in PATH
        if shutil.which("piper") and self.piper_model and os.path.isfile(self.piper_model):
            return True
        return False

    def _start_worker(self):
        """Starts background worker thread consuming the speech queue."""
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _get_pyttsx3(self):
        """Initializes pyttsx3 engine lazily within worker thread."""
        if self._pyttsx3_engine is None:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                engine.setProperty("volume", self.volume)
                if self.voice:
                    engine.setProperty("voice", self.voice)
                self._pyttsx3_engine = engine
            except Exception as e:
                print(f"[Voice TTS Warning] pyttsx3 initialization failed: {e}")
        return self._pyttsx3_engine

    def stop(self):
        """Immediately interrupts speech and clears any queued sentences."""
        self._stop_requested.set()
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except Exception:
                break
        _IS_SPEAKING.clear()
        if self._pyttsx3_engine:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass

    def speak(self, text: str, summarize: bool = False):
        """Queues text to be spoken."""
        self._stop_requested.clear()
        text_to_speak = summarize_for_speech(text) if summarize else text.strip()
        if not text_to_speak:
            return

        # Split text into sentences so playback begins immediately on the first full sentence
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text_to_speak) if s.strip()]
        for s in sentences:
            self._speech_queue.put(s)

    def speak_now(self, text: str):
        """Interrupts current speech and speaks text immediately (blocking until finished)."""
        self.stop()
        self._stop_requested.clear()
        self._play_sentence(text)

    def _worker_loop(self):
        """Processes queued sentences in order."""
        while True:
            try:
                sentence = self._speech_queue.get()
                if sentence is None:
                    break

                if not self._stop_requested.is_set():
                    self._play_sentence(sentence)
                self._speech_queue.task_done()
            except Exception as e:
                _IS_SPEAKING.clear()
                print(f"[Voice TTS Error] Playback exception: {e}")

    def _play_sentence(self, sentence: str):
        """Plays a single sentence with Piper or pyttsx3, asserting _IS_SPEAKING."""
        global _LAST_SPEAKING_TIMESTAMP
        if self._stop_requested.is_set() or not sentence.strip():
            return

        _IS_SPEAKING.set()
        try:
            if self._piper_available:
                self._play_piper(sentence)
            else:
                self._play_pyttsx3(sentence)
        finally:
            # If queue is empty, clear is_speaking flag and note timestamp for 0.5s cooldown
            if self._speech_queue.empty():
                _IS_SPEAKING.clear()
                _LAST_SPEAKING_TIMESTAMP = time.time()

    def _play_piper(self, sentence: str):
        """Synthesizes and plays audio using Piper TTS executable."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_wav_path = tmp_wav.name

        try:
            exe = self.piper_path if self.piper_path and os.path.isfile(self.piper_path) else "piper"
            cmd = [
                exe,
                "--model", self.piper_model,
                "--output_file", tmp_wav_path,
            ]
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.communicate(input=sentence.encode("utf-8"))

            if os.path.exists(tmp_wav_path) and os.path.getsize(tmp_wav_path) > 44:
                import sounddevice as sd
                import wave
                with wave.open(tmp_wav_path, "rb") as wf:
                    data = wf.readframes(wf.getnframes())
                    sample_rate = wf.getframerate()
                    sd.play(data, samplerate=sample_rate)
                    sd.wait()
            else:
                raise RuntimeError("Piper generated empty audio file.")
        except Exception as e:
            print(f"[Voice TTS Error] Piper playback failed ({e}). Falling back to Windows pyttsx3.")
            self._play_pyttsx3(sentence)
        finally:
            try:
                if os.path.exists(tmp_wav_path):
                    os.remove(tmp_wav_path)
            except Exception:
                pass

    def _play_pyttsx3(self, sentence: str):
        """Plays audio using Windows pyttsx3."""
        eng = self._get_pyttsx3()
        if not eng:
            print("[Voice TTS Error] pyttsx3 engine could not be initialized.")
            return

        try:
            eng.say(sentence)
            eng.runAndWait()
        except Exception as e:
            print(f"[Voice TTS Error] pyttsx3 playback exception: {e}")
            self._pyttsx3_engine = None
