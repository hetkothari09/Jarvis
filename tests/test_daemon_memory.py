import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.brain.engine import AssistantTurn, FakeEngine
from jarvis.core.config import Settings
from jarvis.core.daemon import Daemon, _Bridge
from jarvis.memory.service import MemoryService
from jarvis.memory.store import Store
from jarvis.tools.base import Registry


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _daemon_with(engine) -> Daemon:
    d = Daemon.__new__(Daemon)
    d.settings = Settings()
    d.engine = engine
    d.mem = MemoryService(Store(":memory:"), window_min=10, max_facts=100)
    d.registry = Registry()
    d.bridge = _Bridge()
    return d


def _run_work(qapp, daemon, text):
    t = threading.Thread(target=daemon._work, args=(text,))
    t.start()
    for _ in range(200):
        qapp.processEvents()
        if not t.is_alive():
            break
        time.sleep(0.01)
    t.join(timeout=2)
    assert not t.is_alive()


def test_work_records_turns_and_command(qapp):
    eng = FakeEngine([AssistantTurn(text="opened notepad", tool_calls=[])])
    d = _daemon_with(eng)
    _run_work(qapp, d, "open notepad")
    block, turns = d.mem.session_context(now=time.time())
    texts = [t.content if t.role == "user" else t.text for t in turns]
    assert texts == ["open notepad", "opened notepad"]


def test_second_command_sees_prior_turns_as_history(qapp):
    eng = FakeEngine([AssistantTurn(text="one", tool_calls=[]),
                      AssistantTurn(text="two", tool_calls=[])])
    d = _daemon_with(eng)
    _run_work(qapp, d, "first")
    _run_work(qapp, d, "second")
    # the engine's last call must have been seeded with prior turns
    assert eng.last_messages[0].content == "first"
    assert eng.last_messages[-1].content == "second"


def test_open_store_falls_back_on_error(monkeypatch):
    import sqlite3
    import jarvis.core.daemon as d
    real = d.Store
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("unable to open database file")
        return real(":memory:")

    monkeypatch.setattr(d, "Store", flaky)
    store = d._open_store("X:/nonexistent/jarvis.db")
    assert store is not None          # did not raise
    assert calls["n"] == 2            # first failed, fell back to in-memory
