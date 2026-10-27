"""
SuperLocal Voice Assistant: Core Controller Module
Coordinates audio capture, VAD segmentation, live partial transcription,
wake-word & conversation mode (20s follow-up), agent execution, TTS playback,
mic volume diagnostics, and mic selection.
"""

import os
import re
import time
import queue
import threading
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

try:
    import sounddevice as sd
except ImportError:
    sd = None

from config import (
    AUDIO_INPUT_DEVICE,
    AUDIO_OUTPUT_DEVICE,
    VOICE_PTT_KEY,
    VOICE_SAVE_AUDIO,
    WAKE_WORDS,
    CUSTOM_WAKE_WORD,
    MIN_RMS,
    MIN_SPEECH_DURATION,
    TRAILING_SILENCE,
    VAD_THRESHOLD,
    CONVERSATION_TIMEOUT,
    WHISPER_LANGUAGE,
    ENV_FILE,
)
from safety import is_emergency_stopped, trigger_emergency_stop
from voice.wake import WakeWordDetector
from voice.vad import VADProcessor
from voice.stt import SpeechToText, is_hallucination_or_noise
from voice.tts import TextToSpeech, is_tts_speaking, summarize_for_speech
from voice.confirmation import is_dangerous_voice_action, request_voice_confirmation
from voice.audio_retention import save_audio_if_enabled, purge_old_audio_files
from voice.gemini_live import GeminiLiveProvider, GeminiLiveFallbackError

console = Console()

_GLOBAL_VOICE_ASSISTANT: Optional["VoiceAssistant"] = None


def get_voice_assistant(agent=None) -> "VoiceAssistant":
    """Singleton getter for the global VoiceAssistant instance."""
    global _GLOBAL_VOICE_ASSISTANT
    if _GLOBAL_VOICE_ASSISTANT is None:
        _GLOBAL_VOICE_ASSISTANT = VoiceAssistant(agent=agent)
    elif agent is not None:
        _GLOBAL_VOICE_ASSISTANT.agent = agent
    return _GLOBAL_VOICE_ASSISTANT


class VoiceAssistant:
    """
    Main background voice assistant loop for SuperLocal.
    """
    def __init__(
        self,
        agent=None,
        wake_words: Optional[List[str]] = None,
        ptt_key: Optional[str] = None,
        input_device: Optional[Any] = None,
        output_device: Optional[Any] = None,
    ):
        self.agent = agent
        self.input_device = input_device or AUDIO_INPUT_DEVICE
        self.output_device = output_device or AUDIO_OUTPUT_DEVICE

        # Parse device index if numeric string
        if isinstance(self.input_device, str) and self.input_device.isdigit():
            self.input_device = int(self.input_device)
        if isinstance(self.output_device, str) and self.output_device.isdigit():
            self.output_device = int(self.output_device)

        self.wake_detector = WakeWordDetector(wake_words=wake_words, ptt_key=ptt_key)
        self.vad = VADProcessor(
            sample_rate=16000,
            frame_duration_ms=30,
            silence_timeout_sec=TRAILING_SILENCE,
            min_speech_duration_sec=MIN_SPEECH_DURATION,
            energy_threshold=MIN_RMS,
            vad_threshold=VAD_THRESHOLD,
        )
        self.stt = SpeechToText()
        self.tts = TextToSpeech()

        self.is_running = False
        self.is_live_mode = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.status = "IDLE"  # LISTENING, THINKING, SPEAKING, MUTED

        # Conversation Mode timer (20s follow-up window where no wake word is needed)
        self.conversation_until: float = 0.0

        # Silence / no-signal detection tracker
        self._last_signal_time = time.time()
        self._silence_hint_shown = False

        # Live partial transcription tracking
        self._last_partial_time = 0.0
        self._live_display: Optional[Live] = None

        # Audio stream queue
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.block_size = 480  # 30ms frames at 16kHz

    def in_conversation_mode(self) -> bool:
        """Returns True if within the 20-second post-reply conversation window."""
        return time.time() < self.conversation_until

    def start(self, live: bool = False):
        """Starts the voice assistant in a background thread."""
        if self.is_running:
            console.print("[yellow]Voice assistant is already running.[/yellow]")
            return

        self.is_running = True
        self.is_live_mode = live
        self._stop_event.clear()
        self._last_signal_time = time.time()
        self._silence_hint_shown = False

        purge_old_audio_files()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        mode_str = "Gemini Live Mode" if live else "Local Pipeline (Offline & Free)"
        console.print(f"[bold green]SuperLocal Voice Assistant activated ({mode_str}).[/bold green]")
        console.print(f"[dim]Wake word: 'hey superlocal' (or 'hey astra' / F9 Push-To-Talk). Say 'goodbye' to exit.[/dim]\n")

    def stop(self):
        """Stops the voice assistant."""
        self.is_running = False
        self._stop_event.set()
        self.tts.stop()
        self.conversation_until = 0.0
        self.status = "IDLE"
        if self._live_display:
            try:
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None
        console.print("[dim]SuperLocal Voice Assistant deactivated.[/dim]")

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback from sounddevice InputStream."""
        if status:
            pass
        # Mute microphone when SuperLocal is speaking and for 0.5s after
        if is_tts_speaking():
            return
        if self.is_running and not self._stop_event.is_set():
            if indata.dtype == np.float32:
                pcm_data = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            else:
                pcm_data = indata.tobytes()
            self.audio_queue.put(pcm_data)

    def _run_loop(self):
        """Main listening and processing loop."""
        if not sd:
            console.print("[bold red]sounddevice is not installed. Voice mode cannot capture audio.[/bold red]")
            self.is_running = False
            return

        mic_name = "Default Microphone"
        try:
            dev_info = sd.query_devices(self.input_device, "input")
            mic_name = dev_info.get("name", "Default Microphone")
        except Exception:
            pass

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=1,
                dtype="int16",
                device=self.input_device,
                callback=self._audio_callback,
            ):
                self.status = "LISTENING"
                while self.is_running and not self._stop_event.is_set():
                    if is_emergency_stopped():
                        self.tts.stop()
                        time.sleep(0.5)
                        continue

                    # If TTS is actively speaking, drop queued frames and loop
                    if is_tts_speaking():
                        self.status = "SPEAKING"
                        time.sleep(0.05)
                        continue
                    else:
                        if self.status != "THINKING":
                            self.status = "LISTENING"

                    ptt_pressed = self.wake_detector.is_ptt_active()

                    try:
                        frame = self.audio_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    # Check signal presence for 5s warning hint
                    frame_rms = self.vad.compute_rms(frame)
                    if frame_rms > MIN_RMS:
                        self._last_signal_time = time.time()
                    elif (time.time() - self._last_signal_time) > 5.0 and not self._silence_hint_shown:
                        self._silence_hint_shown = True
                        console.print(
                            f"\n[bold yellow]Notice:[/bold yellow] No audio signal detected on microphone '{mic_name}' for 5s.\n"
                            f"[dim]Run /voice devices to check inputs or /voice mic <number> to switch microphone.[/dim]\n"
                        )

                    # Feed frame to VAD
                    is_active_speech, complete_audio = self.vad.process_frame(frame)

                    # Live partial transcript update every ~0.7s while speech is ongoing
                    if is_active_speech and (time.time() - self._last_partial_time) > 0.7:
                        self._last_partial_time = time.time()
                        buf = self.vad.get_current_buffer()
                        if len(buf) >= 9600:  # At least 0.3s of accumulated audio
                            partial_text = self.stt.transcribe_partial(buf)
                            if partial_text:
                                self._update_live_transcript(partial_text)

                    # When a completed utterance is confirmed (>=0.6s speech, >=MIN_RMS, >=0.8s silence)
                    if complete_audio:
                        self._clear_live_transcript()
                        self._process_completed_audio(complete_audio, ptt_pressed=ptt_pressed)

        except Exception as e:
            console.print(f"\n[bold red]Voice loop error:[/bold red] {e}")
            if self.is_live_mode:
                console.print("[yellow]Falling back to SuperLocal local voice pipeline automatically.[/yellow]")
                self.is_live_mode = False
                self._run_loop()
        finally:
            self._clear_live_transcript()
            self.is_running = False
            self.status = "IDLE"

    def _update_live_transcript(self, text: str):
        """Displays live partial transcript on an in-place updating line."""
        try:
            if not self._live_display:
                self._live_display = Live(
                    Text(f"You (live): {text}", style="dim cyan"),
                    console=console,
                    refresh_per_second=4,
                    transient=True,
                )
                self._live_display.start()
            else:
                self._live_display.update(Text(f"You (live): {text}", style="dim cyan"))
        except Exception:
            pass

    def _clear_live_transcript(self):
        """Stops and clears the live partial line."""
        if self._live_display:
            try:
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None

    def _process_completed_audio(self, audio_bytes: bytes, ptt_pressed: bool = False):
        """
        Validates, transcribes, and executes an utterance.
        Transitions to THINKING state ONLY after verifying the clip is non-empty and non-hallucinatory.
        """
        # 1. Transcribe completed audio segment
        transcript, lang, prob = self.stt.transcribe_pcm(audio_bytes)
        clean_transcript = transcript.strip()

        if not clean_transcript or len(clean_transcript) < 2:
            return

        # 2. Check for Voice Stop Words
        t_lower = clean_transcript.lower().rstrip(".!,;?")
        if t_lower in ("stop", "cancel", "quiet", "shut up", "abort", "halt"):
            console.print(f"\n[bold red][VOICE STOP]: '{clean_transcript}'[/bold red]")
            self.tts.stop()
            self.conversation_until = 0.0
            return

        # Check for Voice Exit / Goodbye
        if t_lower in ("goodbye", "good bye", "exit voice", "quit voice", "bye bye"):
            console.print(f"\n[bold cyan]You [{lang}]:[/bold cyan] {clean_transcript}")
            console.print("[bold green]SuperLocal:[/bold green] Goodbye!")
            self.tts.speak_now("Goodbye!")
            self.stop()
            return

        # Filter hallucination artifacts
        if is_hallucination_or_noise(clean_transcript):
            return

        # 3. Check Wake Word or Conversation Mode or Push-To-Talk
        in_conv = self.in_conversation_mode()
        wake_required = not ptt_pressed and not in_conv

        matched, command = self.wake_detector.process_utterance(
            clean_transcript,
            ptt_triggered=ptt_pressed,
            wake_word_required=wake_required,
        )

        if not matched:
            # Ignored speech: does not start with wake word and outside conversation window
            return

        # Now that an authorized, valid command is confirmed, enter THINKING state
        self.status = "THINKING"
        console.print(f"\n[bold cyan]You [{lang}]:[/bold cyan] {clean_transcript}")
        if command != clean_transcript:
            console.print(f"[dim]Command:[/dim] {command}")

        # Save audio if explicitly enabled
        save_audio_if_enabled(audio_bytes, prefix="user_command")

        # 4. Spoken confirmation check for dangerous actions
        is_dang, dang_desc = is_dangerous_voice_action("voice_action", {"command": command})
        if is_dang:
            confirmed = request_voice_confirmation(
                dang_desc,
                tts=self.tts,
                stt=self.stt,
                record_func=self._record_pcm_chunk,
                timeout_sec=15.0,
            )
            if not confirmed:
                self.status = "LISTENING"
                return

        # Check for autopilot voice invocation ("Hey SuperLocal, auto build a todo app")
        cmd_clean = command.strip()
        cmd_lower = cmd_clean.lower()
        if cmd_lower.startswith("auto ") or cmd_lower.startswith("autopilot "):
            goal = re.sub(r'^(?:auto|autopilot)\s+', '', cmd_clean, flags=re.IGNORECASE).strip()
            if goal:
                from autopilot import run_autopilot
                self.status = "THINKING"
                try:
                    job = run_autopilot(goal)
                    summary = f"Job complete: {job.goal[:60]}"
                    self.status = "SPEAKING"
                    self.tts.speak(summary, summarize=False)
                    self.conversation_until = time.time() + CONVERSATION_TIMEOUT
                except Exception as e:
                    self.tts.speak(f"Autopilot error: {e}", summarize=False)
                finally:
                    self.status = "LISTENING"
                return

        # Check for computer mode voice invocation ("Hey SuperLocal, computer, <task>")
        if cmd_lower.startswith("computer ") or cmd_lower.startswith("computer,") or cmd_lower.startswith("@computer"):
            c_task = re.sub(r'^(?:computer,?|@computer)\s*', '', cmd_clean, flags=re.IGNORECASE).strip()
            if c_task:
                from computer import run_computer_mode
                self.status = "THINKING"
                try:
                    res = run_computer_mode(c_task)
                    summary = res.get("summary", "Computer Mode finished.")
                    self.status = "SPEAKING"
                    self.tts.speak(summary, summarize=False)
                    self.conversation_until = time.time() + CONVERSATION_TIMEOUT
                except Exception as e:
                    self.tts.speak(f"Computer Mode error: {e}", summarize=False)
                finally:
                    self.status = "LISTENING"
                return

        # Check for Poki Player voice invocation ("Hey SuperLocal, poki, play 2048")
        if cmd_lower.startswith("poki ") or cmd_lower.startswith("poki,") or cmd_lower.startswith("@poki"):
            poki_task = re.sub(r'^(?:poki,?|@poki)\s*', '', cmd_clean, flags=re.IGNORECASE).strip()
            if poki_task:
                from poki import handle_poki_command
                self.status = "THINKING"
                try:
                    summary = handle_poki_command(f"/poki {poki_task}")
                    self.status = "SPEAKING"
                    self.tts.speak(summary, summarize=True)
                    self.conversation_until = time.time() + CONVERSATION_TIMEOUT
                except Exception as e:
                    self.tts.speak(f"Poki Player error: {e}", summarize=False)
                finally:
                    self.status = "LISTENING"
                return

        # Check for PC Optimizer voice invocation ("Hey SuperLocal, why is my PC slow?")
        if any(trigger in cmd_lower for trigger in ("why is my pc slow", "why is pc slow", "pc slow", "optimize my pc", "clean my pc", "pc optimizer")):
            from optimizer import handle_optimizer_command
            self.status = "THINKING"
            try:
                summary = handle_optimizer_command("/optimize scan")
                self.status = "SPEAKING"
                self.tts.speak(summary, summarize=True)
                self.conversation_until = time.time() + CONVERSATION_TIMEOUT
            except Exception as e:
                self.tts.speak(f"PC Optimizer error: {e}", summarize=False)
            finally:
                self.status = "LISTENING"
            return

        # 5. Route into Agent Loop
        if not self.agent:
            from agent import AstraAgent
            self.agent = AstraAgent()

        try:
            summary = self.agent.run(command)
            if summary:
                console.print(Panel(summary, title="SuperLocal", border_style="green"))
                # Speak short 1-2 sentence version
                self.status = "SPEAKING"
                self.tts.speak(summary, summarize=True)
                # Keep conversation mode active for 20 seconds after reply
                self.conversation_until = time.time() + CONVERSATION_TIMEOUT
        except Exception as e:
            err_msg = f"Sorry, I encountered an error: {e}"
            console.print(f"[bold red]{err_msg}[/bold red]")
            self.tts.speak(err_msg, summarize=False)
        finally:
            self.status = "LISTENING"

    def _record_pcm_chunk(self, duration_sec: float = 2.0) -> bytes:
        """Helper to synchronously record audio for spoken confirmation check."""
        if not sd:
            return b""
        try:
            frames_to_record = int(self.sample_rate * duration_sec)
            recording = sd.rec(
                frames_to_record,
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                device=self.input_device,
            )
            sd.wait()
            return recording.tobytes()
        except Exception:
            return b""


# ==============================================================================
# Helper Functions: Device Listing, Setting, Level Meter & Diagnostics
# ==============================================================================

def list_audio_devices():
    """Prints a formatted table of all audio input and output devices."""
    if not sd:
        console.print("[bold red]sounddevice is not installed.[/bold red]")
        return

    table = Table(title="Audio Devices (Microphones & Speakers)", border_style="cyan")
    table.add_column("Index", style="bold green", justify="right")
    table.add_column("Device Name", style="bold white")
    table.add_column("Channels (In / Out)", style="cyan")
    table.add_column("Host API", style="dim")
    table.add_column("Role", style="magenta")

    devices = sd.query_devices()
    default_in, default_out = sd.default.device

    for idx, d in enumerate(devices):
        role_parts = []
        if idx == default_in:
            role_parts.append("[bold green]Default Mic[/bold green]")
        if idx == default_out:
            role_parts.append("[bold yellow]Default Speaker[/bold yellow]")
        role_str = ", ".join(role_parts) if role_parts else ("Input" if d["max_input_channels"] > 0 else "Output")

        ch_str = f"{d['max_input_channels']} in / {d['max_output_channels']} out"
        table.add_row(str(idx), d["name"], ch_str, str(d.get("hostapi", "")), role_str)

    console.print(table)
    console.print("[dim]To switch microphone: /voice mic <index>[/dim]\n")


def set_audio_mic(mic_index: int) -> bool:
    """Switches the active microphone to the specified index and saves to .env."""
    if not sd:
        console.print("[bold red]sounddevice is not available.[/bold red]")
        return False

    try:
        dev_info = sd.query_devices(mic_index, "input")
        if dev_info.get("max_input_channels", 0) <= 0:
            console.print(f"[bold red]Device {mic_index} ('{dev_info['name']}') has 0 input channels.[/bold red]")
            return False

        mic_name = dev_info["name"]
        va = get_voice_assistant()
        va.input_device = mic_index

        # Save to .env
        env_path = ENV_FILE
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if re.search(r"^AUDIO_INPUT_DEVICE=.*$", content, re.MULTILINE):
                new_content = re.sub(
                    r"^AUDIO_INPUT_DEVICE=.*$",
                    f"AUDIO_INPUT_DEVICE={mic_index}",
                    content,
                    flags=re.MULTILINE,
                )
            else:
                new_content = content + f"\nAUDIO_INPUT_DEVICE={mic_index}\n"
            env_path.write_text(new_content, encoding="utf-8")

        console.print(f"[bold green]Microphone set to device {mic_index} ('{mic_name}'). Choice saved to .env.[/bold green]")
        return True
    except Exception as e:
        console.print(f"[bold red]Failed to set microphone {mic_index}: {e}[/bold red]")
        return False


def show_audio_level(duration_sec: float = 5.0):
    """Displays a live ASCII volume bar for 5 seconds to test microphone sensitivity."""
    if not sd:
        console.print("[bold red]sounddevice is not available.[/bold red]")
        return

    va = get_voice_assistant()
    device = va.input_device

    try:
        dev_info = sd.query_devices(device, "input")
        dev_name = dev_info.get("name", "Default")
    except Exception:
        dev_name = str(device)

    console.print(f"[bold cyan]Showing live volume for '{dev_name}' for {int(duration_sec)} seconds... Speak into mic![/bold cyan]")

    sample_rate = 16000
    block_size = 800  # 50ms updates
    start_time = time.time()

    def rms_to_bar(rms: float) -> str:
        # Scale RMS 0.0 to 0.05 to 0..20 blocks
        level = min(1.0, rms / 0.04)
        blocks = int(level * 20)
        filled = "█" * blocks
        empty = "░" * (20 - blocks)
        pct = int(level * 100)
        return f"[{filled}{empty}] {pct:3d}% (RMS: {rms:.4f})"

    try:
        with sd.InputStream(samplerate=sample_rate, blocksize=block_size, channels=1, dtype="int16", device=device) as stream:
            with Live(console=console, refresh_per_second=10) as live:
                while (time.time() - start_time) < duration_sec:
                    data, _ = stream.read(block_size)
                    samples = data[:, 0].astype(np.float32) / 32768.0
                    rms = float(np.sqrt(np.mean(samples ** 2)))
                    bar_str = rms_to_bar(rms)
                    live.update(Text(f"Mic Level: {bar_str}", style="bold green" if rms > MIN_RMS else "dim yellow"))
                    time.sleep(0.05)
        console.print("[green]Live volume test complete.[/green]\n")
    except Exception as e:
        console.print(f"[bold red]Live level check error: {e}[/bold red]")


def voice_test() -> Dict[str, Any]:
    """
    Executes an end-to-end microphone and speaker diagnostic check.
    Records 2 seconds from microphone, calculates signal energy, tests TTS playback,
    and returns a summary dictionary.
    """
    console.print(Panel(
        "[bold cyan]Running SuperLocal Voice Diagnostic Test...[/bold cyan]\n"
        "1. Checking speaker / TTS engine...\n"
        "2. Recording 2 seconds from microphone...",
        title="Voice Test",
        border_style="cyan"
    ))

    report: Dict[str, Any] = {
        "speaker_status": "Unknown",
        "mic_status": "Unknown",
        "audio_level_rms": 0.0,
        "tts_engine": "Unknown",
    }

    # 1. Test Speaker / TTS
    try:
        tts = TextToSpeech()
        report["tts_engine"] = "piper" if tts._piper_available else "pyttsx3"
        tts.speak_now("SuperLocal voice test active.")
        report["speaker_status"] = "Operational"
        console.print("[green]✔ Speaker and TTS engine operational.[/green]")
    except Exception as e:
        report["speaker_status"] = f"Failed: {e}"
        console.print(f"[red]✘ Speaker / TTS check failed: {e}[/red]")

    # 2. Test Microphone
    if not sd:
        report["mic_status"] = "sounddevice not available"
        return report

    va = get_voice_assistant()
    try:
        sample_rate = 16000
        duration_sec = 2.0
        console.print("[dim]Listening to microphone for 2 seconds (speak now if testing audio level)...[/dim]")
        audio = sd.rec(
            int(sample_rate * duration_sec),
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=va.input_device,
        )
        sd.wait()
        samples = audio[:, 0].astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        report["audio_level_rms"] = round(rms, 4)

        if rms >= MIN_RMS:
            report["mic_status"] = "Operational (Signal Detected)"
            console.print(f"[green]✔ Microphone operational (RMS audio level: {rms:.4f} >= threshold {MIN_RMS}).[/green]")
        else:
            report["mic_status"] = f"Low Signal (RMS: {rms:.4f} < {MIN_RMS})"
            console.print(f"[yellow]⚠ Microphone captured low signal (RMS level: {rms:.4f} < {MIN_RMS}). Increase mic gain or select device via /voice devices.[/yellow]")
    except Exception as e:
        report["mic_status"] = f"Failed: {e}"
        console.print(f"[red]✘ Microphone check failed: {e}[/red]")

    return report
