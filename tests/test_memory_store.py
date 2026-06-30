import pytest
from jarvis.memory.store import Store


@pytest.fixture
def store():
    return Store(":memory:")


def test_fact_add_and_list_newest_first(store):
    store.add_fact("likes dark mode", now=1.0)
    store.add_fact("uses VS Code", key="editor", now=2.0)
    facts = store.list_facts()
    assert facts[0][2] == "uses VS Code" and facts[0][1] == "editor"
    assert facts[1][2] == "likes dark mode"


def test_fact_upsert_by_key_overwrites(store):
    store.add_fact("Sublime", key="editor", now=1.0)
    store.add_fact("VS Code", key="editor", now=2.0)
    editors = [t for _, k, t in store.list_facts() if k == "editor"]
    assert editors == ["VS Code"]


def test_delete_fact_by_id_and_key(store):
    store.add_fact("a", key="k1", now=1.0)
    store.add_fact("b", now=1.0)
    fid = [i for i, k, t in store.list_facts() if t == "b"][0]
    assert store.delete_fact(id=fid) is True
    assert store.delete_fact(key="k1") is True
    assert store.delete_fact(key="missing") is False


def test_note_upsert_get_search_delete(store):
    store.upsert_note("api", "https://x/y", now=1.0)
    store.upsert_note("api", "https://x/z", now=2.0)   # overwrite
    assert store.get_note("api") == "https://x/z"
    assert store.search_notes("x/z") == [("api", "https://x/z")]
    assert store.delete_note("api") is True
    assert store.get_note("api") is None


def test_turns_since_window(store):
    store.add_turn("user", "old", 100.0)
    store.add_turn("user", "recent", 200.0)
    rows = store.turns_since(150.0)
    assert rows == [("user", "recent")]


def test_commands_append(store):
    store.add_command("open notepad", True, "opened", 1.0)
    # no read API needed; just ensure no error and table exists
    assert store.turns_since(0.0) == []


def test_reinit_is_idempotent(tmp_path):
    p = tmp_path / "m.db"
    Store(p).add_fact("x", now=1.0)
    again = Store(p)                      # re-open, schema re-applied
    assert again.list_facts()[0][2] == "x"
