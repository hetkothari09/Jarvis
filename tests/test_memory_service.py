import pytest
from jarvis.memory.store import Store
from jarvis.memory.service import MemoryService


@pytest.fixture
def mem():
    return MemoryService(Store(":memory:"), window_min=10, max_facts=3)


def test_session_context_window_and_facts(mem):
    mem.add_fact("Het", key="name", now=1.0)
    mem.record_turn("user", "old", 100.0)      # 100s, outside 600s window from now=800
    mem.record_turn("user", "hi", 500.0)       # within window
    mem.record_turn("assistant", "hello", 510.0)
    block, turns = mem.session_context(now=800.0)
    assert "- name: Het" in block
    texts = [t.content if t.role == "user" else t.text for t in turns]
    assert texts == ["hi", "hello"]
    assert turns[0].role == "user" and turns[1].role == "assistant"


def test_window_boundary(mem):
    mem.record_turn("user", "in", 200.0)       # now-600 = 200 -> included (>=)
    mem.record_turn("user", "out", 199.0)      # excluded
    _, turns = mem.session_context(now=800.0)
    assert [t.content for t in turns] == ["in"]


def test_facts_cap_and_upsert(mem):       # max_facts=3
    for i in range(5):
        mem.add_fact(f"f{i}", now=float(i))
    block, _ = mem.session_context(now=1000.0)
    assert len(block.splitlines()) == 3        # capped, newest first
    assert "f4" in block and "f0" not in block


def test_forget_fact_by_key_and_note(mem):
    mem.add_fact("VS Code", key="editor", now=1.0)
    assert mem.forget_fact("editor") is True
    mem.add_note("api", "url", now=1.0)
    assert mem.get_note("api") == "url"
    assert mem.forget_note("api") is True
    assert mem.search_notes("url") == []


def test_degrades_when_store_raises():
    class Boom:
        def list_facts(self): raise RuntimeError("db gone")
        def turns_since(self, ts): raise RuntimeError("db gone")
        def add_turn(self, *a): raise RuntimeError("db gone")
    svc = MemoryService(Boom(), window_min=10, max_facts=10)
    assert svc.session_context(now=1.0) == ("", [])
    svc.record_turn("user", "x", 1.0)          # must not raise
