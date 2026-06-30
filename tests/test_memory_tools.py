from jarvis.memory.store import Store
from jarvis.memory.service import MemoryService
from jarvis.tools import build_registry


def _mem():
    return MemoryService(Store(":memory:"), window_min=10, max_facts=100)


def test_remember_recall_and_note_roundtrip():
    mem = _mem()
    reg = build_registry(mem)
    reg.get("remember_fact").run(text="VS Code", key="editor")
    reg.get("save_note").run(key="api", text="https://x/y")

    recall = reg.get("recall").run(query="VS Code")
    assert recall.ok is True
    assert "VS Code" in recall.data["facts"]

    recall_note = reg.get("recall").run(query="x/y")
    assert recall_note.data["notes"] == [("api", "https://x/y")]


def test_forget_removes_fact():
    mem = _mem()
    reg = build_registry(mem)
    reg.get("remember_fact").run(text="VS Code", key="editor")
    res = reg.get("forget").run(key_or_id="editor")
    assert res.ok is True and res.data["removed"] is True
    assert mem.list_facts() == []


def test_build_registry_without_mem_has_no_memory_tools():
    reg = build_registry()
    try:
        reg.get("remember_fact")
        assert False, "memory tools should be absent without mem"
    except KeyError:
        pass
