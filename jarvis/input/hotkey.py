"""Global hotkey listener built on pynput. Runs on its own thread."""
from typing import Callable

from pynput import keyboard


class HotkeyListener:
    def __init__(self, combo: str, on_activate: Callable[[], None]) -> None:
        self._combo = combo
        self._on_activate = on_activate
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        self._listener = keyboard.GlobalHotKeys({self._combo: self._on_activate})
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
