"""
SuperLocal Secure Credential Storage via Keyring
Stores API keys in the Windows Credential Manager (or OS secure store)
ensuring secrets are never persisted in plain text files or logs.
"""

import os
import keyring
from typing import Optional, Dict

SERVICE_NAME = "SuperLocal"

PROVIDER_KEY_MAP = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


def store_credential(provider: str, key_value: str) -> bool:
    """Securely stores provider secret in OS keyring."""
    clean_val = key_value.strip()
    key_name = PROVIDER_KEY_MAP.get(provider.lower(), f"{provider.upper()}_API_KEY")
    try:
        if clean_val:
            keyring.set_password(SERVICE_NAME, key_name, clean_val)
            os.environ[key_name] = clean_val
        else:
            try:
                keyring.delete_password(SERVICE_NAME, key_name)
            except Exception:
                pass
            os.environ.pop(key_name, None)
        return True
    except Exception:
        # Fallback to in-memory environment variable if keyring backend fails
        if clean_val:
            os.environ[key_name] = clean_val
        return True


def retrieve_credential(provider: str) -> Optional[str]:
    """Retrieves secret from OS keyring or environment variable."""
    key_name = PROVIDER_KEY_MAP.get(provider.lower(), f"{provider.upper()}_API_KEY")
    try:
        val = keyring.get_password(SERVICE_NAME, key_name)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key_name)


def mask_credential(val: Optional[str]) -> str:
    """Returns a masked representation (e.g. AIza...4567) without exposing secrets."""
    if not val:
        return ""
    if len(val) <= 8:
        return "•" * len(val)
    return f"{val[:4]}...{val[-4:]}"
