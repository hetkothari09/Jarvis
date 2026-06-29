"""Regression test for the worker-thread -> main-thread confirm handoff.

The dangerous-tool confirm dialog must run on the Qt main thread while the
worker thread blocks for the answer. An earlier version scheduled the dialog
with a worker-thread QTimer, which never fires (no event loop on that thread)
and deadlocked. These tests drive the real Daemon._confirm / _do_confirm across
threads with a bounded event-loop pump, so a deadlock regression fails fast.
"""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.core.daemon import Daemon, _Bridge


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class StubPalette:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.thread_name: str | None = None

    def confirm(self, message: str) -> bool:
        self.thread_name = threading.current_thread().name
        return self.answer


class FakeCall:
    name = "run_shell"
    args = {"command": "echo hi"}


def _make_daemon(palette: StubPalette) -> Daemon:
    # Bypass the heavy __init__ (tray, Anthropic client, API key); wire only the
    # pieces the confirm handoff needs.
    d = Daemon.__new__(Daemon)
    d.bridge = _Bridge()
    d.palette = palette
    d.bridge.confirm_request.connect(d._do_confirm)
    return d


def _run_confirm(qapp, daemon: Daemon) -> dict:
    out: dict = {}
    t = threading.Thread(target=lambda: out.__setitem__("result", daemon._confirm(FakeCall())),
                         name="worker")
    t.start()
    for _ in range(200):                 # ~2s budget
        qapp.processEvents()
        if not t.is_alive():
            break
        time.sleep(0.01)
    t.join(timeout=2)
    assert not t.is_alive(), "confirm deadlocked: dialog never ran on the main thread"
    return out


def test_confirm_runs_on_main_thread_and_returns_true(qapp):
    palette = StubPalette(answer=True)
    out = _run_confirm(qapp, _make_daemon(palette))
    assert out["result"] is True
    assert palette.thread_name == "MainThread"


def test_confirm_returns_false_when_declined(qapp):
    palette = StubPalette(answer=False)
    out = _run_confirm(qapp, _make_daemon(palette))
    assert out["result"] is False
