from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
FALSE_VALUES = {"0", "false", "no", "off"}
_DOTENV_LOADED = False


def load_dotenv(
    path: str | Path | None = None,
    *,
    override: bool = False,
    force: bool = False,
) -> bool:
    """Load a local .env file without adding a runtime dependency."""
    global _DOTENV_LOADED

    if not force and not _should_auto_load_dotenv():
        return False

    env_path = _resolve_env_path(path)
    if env_path is None or not env_path.exists():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if not override and key in os.environ:
            continue
        os.environ[key] = value

    _DOTENV_LOADED = True
    return True


def provider_status() -> dict[str, object]:
    llm_provider = _env_value("LLM_PROVIDER", "fake")
    pronunciation_provider = _env_value("PRON_PROVIDER", "mock")
    asr_provider = _env_value("ASR_PROVIDER", "fake")
    tts_provider = _env_value("TTS_PROVIDER", "browser")
    llm_model = None
    if llm_provider not in {"fake", "none", "disabled"}:
        llm_model = os.environ.get("LLM_MODEL", "").strip() or None

    return {
        "dotenv_loaded": _DOTENV_LOADED,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "asr_provider": asr_provider,
        "pronunciation_provider": pronunciation_provider,
        "tts_provider": tts_provider,
        "external_services_enabled": _external_services_enabled(
            llm_provider=llm_provider,
            pronunciation_provider=pronunciation_provider,
            tts_provider=tts_provider,
        ),
    }


def _should_auto_load_dotenv() -> bool:
    configured = os.environ.get("APP_AUTO_LOAD_DOTENV", "1").strip().lower()
    if configured in FALSE_VALUES:
        return False
    if "pytest" in sys.modules and os.environ.get("APP_TEST_REAL_PROVIDERS") != "1":
        return False
    return True


def _resolve_env_path(path: str | Path | None) -> Path | None:
    configured = path if path is not None else os.environ.get("APP_ENV_FILE")
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path
    return DEFAULT_ENV_PATH


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _env_value(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower() or default


def _external_services_enabled(
    *,
    llm_provider: str,
    pronunciation_provider: str,
    tts_provider: str,
) -> bool:
    return (
        llm_provider not in {"fake", "none", "disabled"}
        or pronunciation_provider not in {"mock", "none", "disabled"}
        or tts_provider not in {"browser", "cloud_disabled", "none", "disabled"}
    )
