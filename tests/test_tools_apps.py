from jarvis.tools.base import Registry
from jarvis.tools import apps


def test_open_app_launches_via_startfile(monkeypatch):
    reg = Registry()
    calls = []
    monkeypatch.setattr(apps, "_launch", lambda target: calls.append(target))
    apps.register(reg)
    result = reg.get("open_app").run(name="notepad")
    assert result.ok is True
    assert calls == ["notepad"]


def test_close_app_kills_matching_processes(monkeypatch):
    reg = Registry()
    killed = []

    class FakeProc:
        def __init__(self, name):
            self.info = {"name": name}
        def kill(self):
            killed.append(self.info["name"])

    monkeypatch.setattr(apps, "_iter_processes",
                        lambda: [FakeProc("notepad.exe"), FakeProc("chrome.exe")])
    apps.register(reg)
    result = reg.get("close_app").run(name="notepad")
    assert result.ok is True
    assert killed == ["notepad.exe"]
    assert result.data["closed"] == 1
