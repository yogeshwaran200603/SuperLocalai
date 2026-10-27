"""
SuperLocal Voice Assistant: Audio Retention Policy
Enforces strict audio privacy: never saves audio unless VOICE_SAVE_AUDIO=true,
and automatically purges any saved recordings older than 24 hours.
"""

import time
import wave
from pathlib import Path
from typing import Optional
from config import VOICE_SAVE_AUDIO, VOICE_DIR


def purge_old_audio_files(directory: Optional[Path] = None, max_age_hours: float = 24.0) -> int:
    """
    Deletes saved audio recordings older than 24 hours.
    Returns the count of purged files.
    """
    target_dir = directory or VOICE_DIR
    if not target_dir.exists():
        return 0

    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    purged_count = 0

    for file_path in target_dir.glob("*.wav"):
        try:
            if file_path.stat().st_mtime < cutoff:
                file_path.unlink()
                purged_count += 1
        except Exception:
            pass

    return purged_count


def save_audio_if_enabled(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    prefix: str = "voice",
    directory: Optional[Path] = None,
) -> Optional[str]:
    """
    Saves audio to disk only if VOICE_SAVE_AUDIO is explicitly enabled.
    Otherwise discards the audio from memory immediately.
    """
    if not VOICE_SAVE_AUDIO or not pcm_bytes:
        return None

    target_dir = directory or VOICE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Purge old recordings whenever saving
    purge_old_audio_files(target_dir, max_age_hours=24.0)

    filename = f"{prefix}_{int(time.time() * 1000)}.wav"
    out_path = target_dir / filename

    try:
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return str(out_path)
    except Exception:
        return None
