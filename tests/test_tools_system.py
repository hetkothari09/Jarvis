from jarvis.tools.base import Registry
from jarvis.tools import system


def test_clipboard_roundtrip(monkeypatch):
    store = {"v": ""}
    monkeypatch.setattr(system, "_clip_set", lambda t: store.__setitem__("v", t))
    monkeypatch.setattr(system, "_clip_get", lambda: store["v"])
    reg = Registry()
    system.register(reg)
    assert reg.get("clipboard_set").run(text="hello").ok is True
    assert reg.get("clipboard_get").run().data["text"] == "hello"


def test_set_volume_clamps_and_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(system, "_apply_volume", lambda pct: seen.append(pct))
    reg = Registry()
    system.register(reg)
    reg.get("set_volume").run(percent=150)
    reg.get("set_volume").run(percent=-5)
    assert seen == [100, 0]


def test_media_key_presses(monkeypatch):
    pressed = []
    monkeypatch.setattr(system, "_press", lambda key: pressed.append(key))
    reg = Registry()
    system.register(reg)
    result = reg.get("media_key").run(key="playpause")
    assert result.ok is True and pressed == ["playpause"]


def test_media_key_rejects_unknown():
    reg = Registry()
    system.register(reg)
    result = reg.get("media_key").run(key="explode")
    assert result.ok is False


def test_run_shell_is_dangerous_and_returns_output(monkeypatch):
    reg = Registry()
    monkeypatch.setattr(system, "_run", lambda cmd: ("hello\n", 0))
    system.register(reg)
    assert reg.get("run_shell").danger is True
    result = reg.get("run_shell").run(command="echo hello")
    assert result.ok is True and "hello" in result.data["stdout"]
