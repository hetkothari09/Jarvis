from pathlib import Path
from jarvis.core.config import Settings


def test_memory_defaults():
    s = Settings()
    assert s.session_window_min == 10
    assert s.max_facts_injected == 100
    assert isinstance(s.data_dir, Path)
    assert s.db_path == s.data_dir / "jarvis.db"


def test_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_SESSION_WINDOW_MIN", "3")
    monkeypatch.setenv("JARVIS_DATA_DIR", str(Path("X:/tmp/jarvisdata")))
    s = Settings()
    assert s.session_window_min == 3
    assert s.data_dir == Path("X:/tmp/jarvisdata")
    assert s.db_path == Path("X:/tmp/jarvisdata") / "jarvis.db"
