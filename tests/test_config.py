from jarvis.core.config import Settings, get_api_key, set_api_key


def test_defaults():
    s = Settings()
    assert s.hotkey == "<ctrl>+<space>"
    assert s.model == "claude-opus-4-8"
    assert s.max_steps == 12


def test_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_MAX_STEPS", "5")
    s = Settings()
    assert s.max_steps == 5


def test_api_key_roundtrip_via_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr("jarvis.core.config.keyring.set_password",
                        lambda svc, user, pw: store.__setitem__((svc, user), pw))
    monkeypatch.setattr("jarvis.core.config.keyring.get_password",
                        lambda svc, user: store.get((svc, user)))
    set_api_key("sk-test")
    assert get_api_key() == "sk-test"
