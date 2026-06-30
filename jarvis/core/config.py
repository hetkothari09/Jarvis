"""User settings (env-overridable) and secret storage (OS keyring)."""
import os
from pathlib import Path

import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE = "jarvis-desktop-agent"
_KEY_USER = "anthropic_api_key"


def _default_data_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "jarvis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    hotkey: str = "<ctrl>+<space>"
    model: str = "claude-opus-4-8"
    max_steps: int = 12
    session_window_min: int = 10
    max_facts_injected: int = 100
    data_dir: Path = _default_data_dir()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.db"


def set_api_key(value: str) -> None:
    keyring.set_password(_SERVICE, _KEY_USER, value)


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _KEY_USER)
