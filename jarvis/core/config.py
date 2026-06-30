"""User settings (env-overridable) and secret storage (OS keyring)."""
import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE = "jarvis-desktop-agent"
_KEY_USER = "anthropic_api_key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    hotkey: str = "<ctrl>+<space>"
    model: str = "claude-opus-4-8"
    max_steps: int = 12


def set_api_key(value: str) -> None:
    keyring.set_password(_SERVICE, _KEY_USER, value)


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _KEY_USER)
