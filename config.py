"""
Astra-Local Configuration Module
Loads environment variables, defines paths, settings, shortcuts, and the Gemini system prompt.
"""

import os
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SCREENS_DIR = LOGS_DIR / "screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)
ACTIONS_LOG_PATH = LOGS_DIR / "actions.log"

SHORTCUTS_PATH = BASE_DIR / "shortcuts.json"

# Load environment variables
load_dotenv(dotenv_path=ENV_FILE)

# API Key & Gemini Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.8-flash").strip()
TAKEOVER_MODEL = os.getenv("TAKEOVER_MODEL", "gemini-2.5-computer-use-preview-10-2025").strip()
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", os.getenv("GEMINI_MODEL", TEXT_MODEL)).strip()
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gemini-3.5-flash-lite").strip()

# Multi-Provider Configuration
DEFAULT_PROVIDER_ORDER = "ollama_local,groq,openrouter,gemini"
raw_provider_order = os.getenv("PROVIDER_ORDER", DEFAULT_PROVIDER_ORDER).strip()
PROVIDER_ORDER = [p.strip() for p in raw_provider_order.split(",") if p.strip()]
if not PROVIDER_ORDER:
    PROVIDER_ORDER = ["ollama_local", "groq", "openrouter", "gemini"]

# Ollama Settings
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()

# OpenAI Compatible / Groq / OpenRouter Settings
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip()

# Vision & Automation Defaults
USE_VISION = os.getenv("USE_VISION", "false").strip().lower() in ("true", "1", "yes")
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish").strip()


def mask_secret(secret: str) -> str:
    """Masks sensitive API keys for safe display (e.g. AIza...wStA) without leaking secrets."""
    if not secret:
        return "Not configured"
    if len(secret) < 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"

raw_chain = os.getenv("MODEL_CHAIN", "").strip()
if raw_chain:
    MODEL_CHAIN = [m.strip() for m in raw_chain.split(",") if m.strip()]
else:
    _default_chain = [
        PRIMARY_MODEL,
        FALLBACK_MODEL,
        "gemini-flash-latest",
    ]
    MODEL_CHAIN = []
    for m in _default_chain:
        if m and m not in MODEL_CHAIN:
            MODEL_CHAIN.append(m)

MODEL_NAME = PRIMARY_MODEL
THINKING_LEVEL = os.getenv("THINKING_LEVEL", "medium").strip().lower()

# Quota & Cache Limits (counter only warns, never blocks a provider)
# Configurable limits with no default of 20 (warn-only, None if unconfigured)
raw_quota = os.getenv("QUOTA_PER_DAY", "").strip()
QUOTA_PER_DAY = int(raw_quota) if raw_quota.isdigit() else None
raw_warn = os.getenv("QUOTA_WARN_THRESHOLD", "").strip()
QUOTA_WARN_THRESHOLD = int(raw_warn) if raw_warn.isdigit() else None
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

# Execution & Watchdog Limits
MAX_STEPS = int(os.getenv("MAX_STEPS", "8"))
MAX_DESKTOP_ACTIONS = int(os.getenv("MAX_DESKTOP_ACTIONS", "25"))
POWERSHELL_TIMEOUT = int(os.getenv("POWERSHELL_TIMEOUT", "60"))
PYTHON_TIMEOUT = int(os.getenv("PYTHON_TIMEOUT", "60"))
TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "30"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "600"))  # 10 minutes default
SLOW_STEP_THRESHOLD = 10.0
SLOW_STEPS_LOG_PATH = LOGS_DIR / "slow_steps.log"

# All configured provider keys for comprehensive masking
ALL_API_KEYS = [
    k for k in [
        GEMINI_API_KEY,
        GROQ_API_KEY,
        OPENROUTER_API_KEY,
        OPENAI_API_KEY,
        OLLAMA_API_KEY,
    ] if k and len(k) > 4
]

# Safety Configuration
AUTO_APPROVE_SAFE = os.getenv("AUTO_APPROVE_SAFE", "false").strip().lower() in ("true", "1", "yes")

# Allowed Workspaces & Paths
USER_PROFILE = Path(os.environ.get("USERPROFILE", str(Path.home()))).resolve()
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
if WORKSPACE_DIR:
    WORKSPACE_DIR = Path(os.path.expandvars(WORKSPACE_DIR)).resolve()
else:
    WORKSPACE_DIR = USER_PROFILE / "astra_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

DESKTOP_DIR = USER_PROFILE / "Desktop"
DOCUMENTS_DIR = USER_PROFILE / "Documents"
DOWNLOADS_DIR = USER_PROFILE / "Downloads"
TEMP_DIR = Path(tempfile.gettempdir()).resolve()

ALLOWED_DIRECTORIES = [
    WORKSPACE_DIR,
    DESKTOP_DIR,
    DOCUMENTS_DIR,
    DOWNLOADS_DIR,
    BASE_DIR,
    TEMP_DIR,
]

# Database Path
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "astra_memory.db"

# Browser Persistent Data Directory (keeps WhatsApp QR login, cookies, etc.)
BROWSER_USER_DATA_DIR = os.getenv("BROWSER_USER_DATA_DIR")
if BROWSER_USER_DATA_DIR:
    BROWSER_USER_DATA_DIR = Path(os.path.expandvars(BROWSER_USER_DATA_DIR)).resolve()
else:
    BROWSER_USER_DATA_DIR = USER_PROFILE / ".astra_local" / "browser_data"
BROWSER_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_shortcuts() -> dict:
    """Loads shortcuts from shortcuts.json and expands environment variables."""
    if not SHORTCUTS_PATH.exists():
        return {}
    try:
        with open(SHORTCUTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Expand environment variables in string values
            def _expand(obj):
                if isinstance(obj, dict):
                    return {k: _expand(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_expand(i) for i in obj]
                elif isinstance(obj, str):
                    return os.path.expandvars(obj)
                return obj
            return _expand(data)
    except Exception:
        return {}


def get_system_prompt() -> str:
    """Returns the system prompt with user shortcuts injected."""
    shortcuts = load_shortcuts()
    shortcuts_str = json.dumps(shortcuts, indent=2)

    return (
        "You are Superlocal, an assistant that controls a Windows PC created by Yogeshwaran. "
        "Choose the simplest reliable method: a PowerShell script or deep link first, "
        "then browser automation, then desktop clicking as the last resort. "
        "Use shortcuts.json for known names. "
        "Never invent IDs or paths; if something is unknown, ask the user. "
        "Write safe, minimal PowerShell. After each step, check the result before continuing.\n\n"
        f"Known Shortcuts (from shortcuts.json):\n{shortcuts_str}\n\n"
        f"Default Directories:\n"
        f"- Desktop: {DESKTOP_DIR}\n"
        f"- Documents: {DOCUMENTS_DIR}\n"
        f"- Downloads: {DOWNLOADS_DIR}\n"
        f"- Workspace: {WORKSPACE_DIR}\n\n"
        "Guidelines:\n"
        "1. For launching Discord servers, look up the server ID in discord_servers shortcuts and run Start-Process \"discord://-/channels/SERVER_ID/CHANNEL_ID\".\n"
        "2. For WhatsApp messages, call whatsapp_send(contact, message).\n"
        "3. For web tasks or testing websites, use the dedicated browser tools.\n"
        "4. For data analysis (.csv, .xlsx), use data_tools (data_inspect, data_clean, data_chart).\n"
        "5. For presentations and office documents, use docs_tools (doc_create_pptx, doc_create_docx, etc.).\n"
        "6. For software scaffolding and testing, use dev_tools.\n"
        "7. For file operations, prefer file_read, file_write, file_list or PowerShell.\n"
        "8. QUOTA OPTIMIZATION & PARALLEL BATCHING: Return multiple independent tool calls in a single turn whenever feasible. Do not serialize steps across unnecessary turns. Finish tasks in as few turns as possible.\n"
        "9. Always be concise, verify outcomes, and provide a clear final summary."
    )


def get_small_model_system_prompt() -> str:
    """Concise, high-impact system prompt tailored for smaller local models (e.g. Qwen, Llama)."""
    return (
        "You are Superlocal, a Windows PC assistant created by Yogeshwaran. "
        "Use the provided tools to fulfill requests safely and accurately. "
        "Priority order: PowerShell scripts or deep links first, then browser, then desktop clicking. "
        "When calling tools, provide valid arguments strictly matching the parameter types in the schema. "
        "Keep answers concise and clear."
    )


# ==============================================================================
# Voice Assistant Configuration
# ==============================================================================
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").strip().lower() in ("true", "1", "yes")

# Wake Words (default: hey superlocal, hey astra, superlocal; customizable)
CUSTOM_WAKE_WORD = os.getenv("CUSTOM_WAKE_WORD", "").strip().lower()
_raw_wake = os.getenv("WAKE_WORDS", "hey superlocal,hey astra,superlocal").strip().lower()
WAKE_WORDS = [w.strip() for w in _raw_wake.split(",") if w.strip()]
if CUSTOM_WAKE_WORD and CUSTOM_WAKE_WORD not in WAKE_WORDS:
    WAKE_WORDS.insert(0, CUSTOM_WAKE_WORD)

VOICE_PTT_KEY = os.getenv("VOICE_PTT_KEY", "f9").strip().lower()

# Faster-Whisper Speech-to-Text Settings
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base").strip()
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()
raw_whisper_lang = os.getenv("WHISPER_LANGUAGE", "auto").strip().lower()
WHISPER_LANGUAGE = None if raw_whisper_lang in ("", "auto", "none") else raw_whisper_lang

# Voice Activity Detection (VAD) & Audio Thresholds
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
MIN_RMS = float(os.getenv("MIN_RMS", "0.008"))
MIN_SPEECH_DURATION = float(os.getenv("MIN_SPEECH_DURATION", "0.6"))
TRAILING_SILENCE = float(os.getenv("TRAILING_SILENCE", "0.8"))
CONVERSATION_TIMEOUT = float(os.getenv("CONVERSATION_TIMEOUT", "20.0"))

# Text-to-Speech Settings (Piper if available, else pyttsx3 Windows voices)
TTS_ENGINE = os.getenv("TTS_ENGINE", "auto").strip().lower()
PIPER_PATH = os.getenv("PIPER_PATH", "").strip()
PIPER_MODEL = os.getenv("PIPER_MODEL", "").strip()
TTS_VOICE = os.getenv("TTS_VOICE", "").strip()
TTS_RATE = int(os.getenv("TTS_RATE", "180"))
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "1.0"))

# Audio Device Settings (None = system default)
AUDIO_INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "").strip() or None
AUDIO_OUTPUT_DEVICE = os.getenv("AUDIO_OUTPUT_DEVICE", "").strip() or None

# Gemini Live Model & Realtime Endpoint
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-2.0-flash-exp").strip()

# Voice Audio Retention & Safety
VOICE_SAVE_AUDIO = os.getenv("VOICE_SAVE_AUDIO", "false").strip().lower() in ("true", "1", "yes")
VOICE_DIR = LOGS_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# Autopilot End-to-End Mode Configuration
# ==============================================================================
AUTOPILOT_MAX_STEPS = int(os.getenv("AUTOPILOT_MAX_STEPS", "40"))
AUTOPILOT_MAX_MINUTES = int(os.getenv("AUTOPILOT_MAX_MINUTES", "30"))
AUTOPILOT_MAX_MODEL_CALLS = int(os.getenv("AUTOPILOT_MAX_MODEL_CALLS", "25"))
AUTOPILOT_MAX_DESKTOP_ACTIONS = int(os.getenv("AUTOPILOT_MAX_DESKTOP_ACTIONS", "30"))
AUTO_APPROVE_LOW_RISK = os.getenv("AUTO_APPROVE_LOW_RISK", "false").strip().lower() in ("true", "1", "yes")

# Autopilot Jobs Directory inside Workspace
JOBS_DIR = WORKSPACE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
if JOBS_DIR not in ALLOWED_DIRECTORIES:
    ALLOWED_DIRECTORIES.append(JOBS_DIR)

# ==============================================================================
# Computer Mode (@computer) Configuration
# ==============================================================================
COMPUTER_DEFAULT_EFFORT = os.getenv("COMPUTER_DEFAULT_EFFORT", "medium").lower()
COMPUTER_EFFORT_LOW_MAX_ACTIONS = int(os.getenv("COMPUTER_EFFORT_LOW_MAX_ACTIONS", "10"))
COMPUTER_EFFORT_MED_MAX_ACTIONS = int(os.getenv("COMPUTER_EFFORT_MED_MAX_ACTIONS", "30"))
COMPUTER_EFFORT_HIGH_MAX_ACTIONS = int(os.getenv("COMPUTER_EFFORT_HIGH_MAX_ACTIONS", "80"))
COMPUTER_EFFORT_HIGH_MAX_MINUTES = int(os.getenv("COMPUTER_EFFORT_HIGH_MAX_MINUTES", "60"))
COMPUTER_ACTION_PAUSE = float(os.getenv("COMPUTER_ACTION_PAUSE", "0.3"))
COMPUTER_VISION_MAX_WIDTH = int(os.getenv("COMPUTER_VISION_MAX_WIDTH", "1024"))
COMPUTER_VISION_JPEG_QUALITY = int(os.getenv("COMPUTER_VISION_JPEG_QUALITY", "50"))
SAVE_SCREENS = os.getenv("SAVE_SCREENS", "false").strip().lower() in ("true", "1", "yes")

# ==============================================================================
# Poki Player (Games Workbench) Configuration
# ==============================================================================
POKI_MAX_MINUTES = int(os.getenv("POKI_MAX_MINUTES", "20"))
POKI_MAX_RUNS = int(os.getenv("POKI_MAX_RUNS", "50"))
POKI_TARGET_FPS = int(os.getenv("POKI_TARGET_FPS", "24"))
POKI_LOG_PATH = LOGS_DIR / "poki.log"
POKI_STATS_PATH = DATA_DIR / "poki_stats.json"
POKI_REPLAYS_DIR = LOGS_DIR / "poki_replays"
POKI_REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
SAVE_VIDEO = os.getenv("SAVE_VIDEO", "false").strip().lower() in ("true", "1", "yes")

# ==============================================================================
# PC Optimizer Workbench Configuration
# ==============================================================================
OPTIMIZER_CLEAN_MIN_AGE_DAYS = int(os.getenv("OPTIMIZER_CLEAN_MIN_AGE_DAYS", "7"))
OPTIMIZER_LOG_PATH = LOGS_DIR / "optimizer.log"
OPTIMIZER_QUARANTINE_DIR = DATA_DIR / "optimizer_quarantine"
OPTIMIZER_QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
OPTIMIZER_STARTUP_BACKUP = DATA_DIR / "optimizer_startup_backup.json"
OPTIMIZER_REPORTS_DIR = DATA_DIR / "optimizer_reports"
OPTIMIZER_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OPTIMIZER_SCHEDULE_DAY = os.getenv("OPTIMIZER_SCHEDULE_DAY", "Sunday")



