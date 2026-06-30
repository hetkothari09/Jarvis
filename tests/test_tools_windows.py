from jarvis.tools.base import Registry
from jarvis.tools import windows


class FakeWin:
    def __init__(self, title):
        self.title = title
        self.activated = False
        self.box = None
    def activate(self):
        self.activated = True
    def moveTo(self, x, y):
        self.box = (x, y)
    def resizeTo(self, w, h):
        self.box = (self.box or (0, 0)) + (w, h)


def test_focus_window_activates_first_match(monkeypatch):
    reg = Registry()
    win = FakeWin("Google Chrome")
    monkeypatch.setattr(windows, "_find_windows", lambda title: [win] if "chrome" in title.lower() else [])
    windows.register(reg)
    result = reg.get("focus_window").run(title="chrome")
    assert result.ok is True and win.activated is True


def test_focus_window_no_match_returns_error(monkeypatch):
    reg = Registry()
    monkeypatch.setattr(windows, "_find_windows", lambda title: [])
    windows.register(reg)
    result = reg.get("focus_window").run(title="nope")
    assert result.ok is False and "no window" in result.error.lower()


def test_arrange_window_snaps_left(monkeypatch):
    reg = Registry()
    win = FakeWin("Editor")
    monkeypatch.setattr(windows, "_find_windows", lambda title: [win])
    monkeypatch.setattr(windows, "_screen_size", lambda: (1920, 1080))
    windows.register(reg)
    result = reg.get("arrange_window").run(title="Editor", position="left")
    assert result.ok is True
    assert win.box == (0, 0, 960, 1080)
