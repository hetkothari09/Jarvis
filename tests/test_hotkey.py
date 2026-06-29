from jarvis.input import hotkey


def test_hotkey_listener_invokes_callback_on_activate(monkeypatch):
    captured = {}

    class FakeHotKeys:
        def __init__(self, mapping):
            captured["mapping"] = mapping
        def start(self):
            captured["started"] = True
        def join(self):
            pass

    monkeypatch.setattr(hotkey.keyboard, "GlobalHotKeys", FakeHotKeys)
    fired = []
    listener = hotkey.HotkeyListener("<ctrl>+<space>", on_activate=lambda: fired.append(True))
    listener.start()
    captured["mapping"]["<ctrl>+<space>"]()
    assert fired == [True]
    assert captured["started"] is True
