"""Compose all modules into a running tray application."""
import logging
import threading
import time

_log = logging.getLogger(__name__)


def _open_store(path) -> "Store":
    """Open the memory store, falling back to an in-memory store if the on-disk
    DB can't be opened (corrupt, locked, or unwritable dir). A storage failure
    must never prevent the agent from starting."""
    try:
        return Store(path)
    except Exception:
        _log.exception("memory store open failed; using in-memory store")
        return Store(":memory:")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from anthropic import Anthropic

from jarvis.brain.claude_engine import ClaudeEngine
from jarvis.memory.service import MemoryService
from jarvis.memory.store import Store
from jarvis.brain.engine import ToolCall
from jarvis.brain.router import run_command
from jarvis.core.config import Settings, get_api_key
from jarvis.gui.orb import Orb
from jarvis.gui.palette import Palette
from jarvis.gui.theme import ACCENT
from jarvis.input.hotkey import HotkeyListener
from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult


class _Bridge(QObject):
    """Marshals worker-thread events back onto the Qt main thread."""
    step = Signal(str)
    done = Signal(str)
    state = Signal(str)
    summon = Signal()
    confirm_request = Signal(object)  # payload: (call, result_dict, done_event)


def _tray_icon() -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    p.drawEllipse(6, 6, 20, 20)
    p.end()
    return QIcon(pix)


class Daemon:
    def __init__(self) -> None:
        self.settings = Settings()
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)

        key = get_api_key()
        if not key:
            raise SystemExit(
                "No API key. Set one:\n"
                "  python -c \"from jarvis.core.config import set_api_key; "
                "set_api_key('sk-ant-...')\"")
        self.engine = ClaudeEngine(client=Anthropic(api_key=key), model=self.settings.model)
        self.mem = MemoryService(
            _open_store(self.settings.db_path),
            window_min=self.settings.session_window_min,
            max_facts=self.settings.max_facts_injected)
        self.registry = build_registry(self.mem)

        self.orb = Orb()
        self.palette = Palette()
        self.bridge = _Bridge()

        self.bridge.step.connect(self.palette.show_step)
        self.bridge.done.connect(self.palette.show_result)
        self.bridge.state.connect(self.orb.set_state)
        self.bridge.summon.connect(self.palette.summon)
        # Emitted from the worker thread; AutoConnection makes it a queued call
        # dispatched on the main (Qt) thread, where the modal can safely run.
        self.bridge.confirm_request.connect(self._do_confirm)
        self.palette.submitted.connect(self._on_command)

        self.tray = QSystemTrayIcon(_tray_icon())
        menu = QMenu()
        quit_action = QAction("Quit JARVIS")
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("JARVIS")
        self.tray.show()

        self.hotkey = HotkeyListener(self.settings.hotkey,
                                     on_activate=self.bridge.summon.emit)

    def _on_command(self, text: str) -> None:
        threading.Thread(target=self._work, args=(text,), daemon=True).start()

    def _work(self, text: str) -> None:
        self.bridge.state.emit("busy")
        now = time.time()
        facts, turns = self.mem.session_context(now)
        self.mem.record_turn("user", text, now)

        def on_step(call: ToolCall, result: ToolResult) -> None:
            status = "ok" if result.ok else f"error: {result.error}"
            self.bridge.step.emit(f"› {call.name} — {status}")

        def confirm(call: ToolCall) -> bool:
            return self._confirm(call)

        errored = False
        try:
            answer = run_command(text, self.registry, self.engine,
                                 confirm=confirm, on_step=on_step,
                                 max_steps=self.settings.max_steps,
                                 history=turns, memory_context=facts)
            self.bridge.done.emit(answer)
            self.bridge.state.emit("idle")
        except Exception as exc:  # network/engine failure
            errored = True
            answer = f"Error: {exc}"
            self.bridge.done.emit(answer)
            self.bridge.state.emit("error")

        self.mem.record_turn("assistant", answer, time.time())
        self.mem.record_command(text, ok=not errored, summary=answer[:200], ts=now)

    def _confirm(self, call: ToolCall) -> bool:
        """Called on the worker thread. Hand the modal to the main thread and block
        until the user answers. The queued `confirm_request` signal guarantees the
        dialog runs inside the main thread's event loop (no worker-thread timer,
        which would never fire and deadlock)."""
        result: dict = {}
        done = threading.Event()
        self.bridge.confirm_request.emit((call, result, done))
        done.wait()
        return bool(result.get("ok"))

    def _do_confirm(self, payload: tuple) -> None:
        """Runs on the main (Qt) thread via the queued confirm_request signal."""
        call, result, done = payload
        try:
            result["ok"] = self.palette.confirm(
                f"JARVIS wants to run a sensitive action:\n\n"
                f"{call.name}({call.args})\n\nAllow?")
        finally:
            done.set()

    def run(self) -> int:
        self.orb.show()
        self.hotkey.start()
        return self.app.exec()
