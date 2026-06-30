# JARVIS Phase 2a — Memory & State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the stateless Phase-1 brain persistent memory — durable facts/prefs, time-window conversation continuity, append-only command history, and named notes — backed by sqlite.

**Architecture:** New `jarvis/memory/` package: `store.py` (sqlite CRUD), `service.py` (`MemoryService` high-level API with windowing + graceful degradation), `tools.py` (model-facing memory tools). The router gains two optional, backward-compatible params (`history`, `memory_context`); the daemon owns a `MemoryService` and supplies/persists context around each run. Spec: `docs/superpowers/specs/2026-06-30-jarvis-phase2-memory-design.md`.

**Tech Stack:** Python 3, sqlite3 (stdlib — **no new deps**), pydantic-settings, PySide6 (existing), pytest.

## Global Constraints

- **No new external dependencies.** sqlite3 is stdlib.
- **TDD:** failing test → minimal code → green → commit, per task.
- **Memory must never break a command:** every `MemoryService` store access is wrapped; on any error it degrades (empty context / no-op write), never raises into the command path.
- **Backward compatible:** existing 16 Phase-1 test files must stay green. `run_command` new params default to `history=None`, `memory_context=""`. `Engine.complete` gains a trailing `system: str = ""` with a `SYSTEM_PROMPT` fallback so existing 2-arg `complete(...)` calls keep working.
- **Branch:** `jarvis-phase2-memory`.
- **Windows:** DB at `%APPDATA%\jarvis\jarvis.db`; tests use a temp file or `:memory:`.
- Follow Phase-1 conventions: `register(reg)`-style module registration, `ToolResult.ok(...)` / `ToolResult.err(...)`, Anthropic tool schema (`name`/`description`/`input_schema`).

---

### Task 1: Config additions

**Files:**
- Modify: `jarvis/core/config.py`
- Test: `tests/test_config_memory.py`

**Interfaces:**
- Consumes: existing `Settings(BaseSettings)`.
- Produces: `Settings.session_window_min: int = 10`, `Settings.max_facts_injected: int = 100`, `Settings.data_dir: Path` (default `%APPDATA%\jarvis`), `Settings.db_path: Path` property (`data_dir / "jarvis.db"`). Env overrides via `JARVIS_` prefix.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_memory.py
from pathlib import Path
from jarvis.core.config import Settings


def test_memory_defaults():
    s = Settings()
    assert s.session_window_min == 10
    assert s.max_facts_injected == 100
    assert isinstance(s.data_dir, Path)
    assert s.db_path == s.data_dir / "jarvis.db"


def test_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_SESSION_WINDOW_MIN", "3")
    monkeypatch.setenv("JARVIS_DATA_DIR", str(Path("X:/tmp/jarvisdata")))
    s = Settings()
    assert s.session_window_min == 3
    assert s.data_dir == Path("X:/tmp/jarvisdata")
    assert s.db_path == Path("X:/tmp/jarvisdata") / "jarvis.db"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_memory.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'session_window_min'`).

- [ ] **Step 3: Write minimal implementation**

Edit `jarvis/core/config.py`. Add imports at top and the new fields/property:

```python
"""User settings (env-overridable) and secret storage (OS keyring)."""
import os
from pathlib import Path

import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE = "jarvis-desktop-agent"
_KEY_USER = "anthropic_api_key"


def _default_data_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "jarvis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    hotkey: str = "<ctrl>+<space>"
    model: str = "claude-opus-4-8"
    max_steps: int = 12
    session_window_min: int = 10
    max_facts_injected: int = 100
    data_dir: Path = _default_data_dir()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.db"
```

(Keep the existing `set_api_key` / `get_api_key` functions unchanged below.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_memory.py tests/test_config.py -v`
Expected: PASS (new tests + existing config tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/config.py tests/test_config_memory.py
git commit -m "feat: memory settings (data_dir, db_path, session window, facts cap)"
```

---

### Task 2: sqlite Store

**Files:**
- Create: `jarvis/memory/__init__.py` (empty)
- Create: `jarvis/memory/store.py`
- Test: `tests/test_memory_store.py`

**Interfaces:**
- Consumes: nothing (stdlib `sqlite3`, `threading`, `pathlib`).
- Produces: `Store(path: Path | str)` with methods:
  `add_fact(text, key=None, *, now)`, `list_facts() -> list[tuple[int, str|None, str]]` (id, key, text; newest first), `delete_fact(*, id=None, key=None) -> bool`,
  `upsert_note(key, text, *, now)`, `get_note(key) -> str|None`, `search_notes(query) -> list[tuple[str, str]]` (key, text), `delete_note(key) -> bool`,
  `add_turn(role, text, ts)`, `turns_since(ts) -> list[tuple[str, str]]` (role, text; oldest first),
  `add_command(text, ok, summary, ts)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_store.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_store.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'jarvis.memory'`).

- [ ] **Step 3: Write minimal implementation**

Create `jarvis/memory/__init__.py` (empty file).

Create `jarvis/memory/store.py`:

```python
"""sqlite persistence for memory. Thin CRUD; no business logic.

A single connection is shared across daemon worker threads, guarded by a lock.
"""
import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT, text TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL, text TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL, text TEXT NOT NULL, ok INTEGER NOT NULL, summary TEXT);
"""


class Store:
    def __init__(self, path: "Path | str") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # --- facts ---
    def add_fact(self, text: str, key: "str | None" = None, *, now: float) -> None:
        with self._lock:
            if key is not None:
                self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            self._conn.execute(
                "INSERT INTO facts (key, text, created_at) VALUES (?, ?, ?)",
                (key, text, now))
            self._conn.commit()

    def list_facts(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, key, text FROM facts ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [(r["id"], r["key"], r["text"]) for r in rows]

    def delete_fact(self, *, id: "int | None" = None, key: "str | None" = None) -> bool:
        with self._lock:
            if id is not None:
                cur = self._conn.execute("DELETE FROM facts WHERE id = ?", (id,))
            else:
                cur = self._conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    # --- notes ---
    def upsert_note(self, key: str, text: str, *, now: float) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO notes (key, text, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       text = excluded.text, updated_at = excluded.updated_at""",
                (key, text, now, now))
            self._conn.commit()

    def get_note(self, key: str) -> "str | None":
        with self._lock:
            row = self._conn.execute(
                "SELECT text FROM notes WHERE key = ?", (key,)).fetchone()
        return row["text"] if row else None

    def search_notes(self, query: str) -> list:
        like = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, text FROM notes WHERE key LIKE ? OR text LIKE ?",
                (like, like)).fetchall()
        return [(r["key"], r["text"]) for r in rows]

    def delete_note(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM notes WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    # --- turns ---
    def add_turn(self, role: str, text: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (ts, role, text) VALUES (?, ?, ?)",
                (ts, role, text))
            self._conn.commit()

    def turns_since(self, ts: float) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, text FROM turns WHERE ts >= ? ORDER BY ts ASC, id ASC",
                (ts,)).fetchall()
        return [(r["role"], r["text"]) for r in rows]

    # --- commands ---
    def add_command(self, text: str, ok: bool, summary: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO commands (ts, text, ok, summary) VALUES (?, ?, ?, ?)",
                (ts, text, 1 if ok else 0, summary))
            self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_store.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/memory/__init__.py jarvis/memory/store.py tests/test_memory_store.py
git commit -m "feat: sqlite Store for facts, notes, turns, commands"
```

---

### Task 3: MemoryService

**Files:**
- Create: `jarvis/memory/service.py`
- Test: `tests/test_memory_service.py`

**Interfaces:**
- Consumes: `Store` (Task 2), `Msg` from `jarvis.brain.engine`.
- Produces: `MemoryService(store, *, window_min=10, max_facts=100)` with:
  `session_context(now: float) -> tuple[str, list[Msg]]` (facts block string + turn `Msg`s within window),
  `record_turn(role, text, ts)`, `record_command(text, ok, summary, ts)`,
  `add_fact(text, key=None, *, now)`, `list_facts()`, `forget_fact(id_or_key) -> bool`,
  `add_note(key, text, *, now)`, `get_note(key)`, `search_notes(query)`, `forget_note(key) -> bool`.
  All read methods degrade to safe empties on store error; all writes are no-ops on error. Turn `Msg`s use `content` for user role and `text` for assistant role.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_service.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_service.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'jarvis.memory.service'`).

- [ ] **Step 3: Write minimal implementation**

Create `jarvis/memory/service.py`:

```python
"""High-level memory API. Hides sqlite, windowing, and fact rendering, and
degrades gracefully so a storage failure never breaks a command."""
import logging

from jarvis.brain.engine import Msg

log = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, store, *, window_min: int = 10, max_facts: int = 100) -> None:
        self._store = store
        self._window_s = window_min * 60
        self._max_facts = max_facts

    def session_context(self, now: float) -> tuple:
        try:
            facts = self._store.list_facts()[: self._max_facts]
            block = "\n".join(self._render_fact(k, t) for _, k, t in facts)
            rows = self._store.turns_since(now - self._window_s)
            turns = [self._turn_msg(role, text) for role, text in rows]
            return block, turns
        except Exception:
            log.exception("memory session_context failed")
            return "", []

    @staticmethod
    def _render_fact(key, text) -> str:
        return f"- {key}: {text}" if key else f"- {text}"

    @staticmethod
    def _turn_msg(role: str, text: str) -> Msg:
        if role == "assistant":
            return Msg(role="assistant", text=text)
        return Msg(role="user", content=text)

    def record_turn(self, role: str, text: str, ts: float) -> None:
        self._safe(lambda: self._store.add_turn(role, text, ts))

    def record_command(self, text: str, ok: bool, summary: str, ts: float) -> None:
        self._safe(lambda: self._store.add_command(text, ok, summary, ts))

    def add_fact(self, text: str, key=None, *, now: float) -> None:
        self._safe(lambda: self._store.add_fact(text, key, now=now))

    def list_facts(self) -> list:
        return self._safe(lambda: self._store.list_facts(), default=[])

    def forget_fact(self, id_or_key) -> bool:
        return bool(self._safe(
            lambda: self._store.delete_fact(**self._fact_selector(id_or_key)),
            default=False))

    def add_note(self, key: str, text: str, *, now: float) -> None:
        self._safe(lambda: self._store.upsert_note(key, text, now=now))

    def get_note(self, key: str):
        return self._safe(lambda: self._store.get_note(key), default=None)

    def search_notes(self, query: str) -> list:
        return self._safe(lambda: self._store.search_notes(query), default=[])

    def forget_note(self, key: str) -> bool:
        return bool(self._safe(lambda: self._store.delete_note(key), default=False))

    @staticmethod
    def _fact_selector(id_or_key) -> dict:
        s = str(id_or_key)
        return {"id": int(s)} if s.isdigit() else {"key": s}

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            log.exception("memory operation failed")
            return default
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add jarvis/memory/service.py tests/test_memory_service.py
git commit -m "feat: MemoryService with time-window context and graceful degradation"
```

---

### Task 4: Engine `system` param + router `history`/`memory_context`

**Files:**
- Modify: `jarvis/brain/engine.py` (Protocol + `FakeEngine`)
- Modify: `jarvis/brain/claude_engine.py` (`complete` signature)
- Modify: `jarvis/brain/router.py` (`run_command` params + system assembly)
- Test: `tests/test_router_memory.py`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `Msg`, `AssistantTurn`, `FakeEngine`.
- Produces:
  `Engine.complete(messages, tools, system: str = "")`;
  `FakeEngine` records `last_messages`, `last_tools`, `last_system`;
  `ClaudeEngine.complete(messages, tools, system="")` sends `system=system or SYSTEM_PROMPT`;
  `run_command(text, registry, engine, *, confirm, on_step, max_steps=12, history=None, memory_context="")` — prepends `history` Msgs before the user msg and passes a composed system string to the engine.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router_memory.py
from jarvis.brain.engine import AssistantTurn, Msg, FakeEngine
from jarvis.brain.router import run_command, SYSTEM_PROMPT
from jarvis.tools.base import Registry


def _noop_step(call, res):
    pass


def test_history_and_memory_context_reach_engine():
    eng = FakeEngine([AssistantTurn(text="done", tool_calls=[])])
    history = [Msg(role="user", content="open notepad"),
               Msg(role="assistant", text="opened notepad")]
    out = run_command("do it again", Registry(), eng,
                      confirm=lambda c: True, on_step=_noop_step,
                      history=history, memory_context="- name: Het")
    assert out == "done"
    assert eng.last_messages[0].content == "open notepad"
    assert eng.last_messages[-1].content == "do it again"
    assert "Known about the user:" in eng.last_system
    assert "- name: Het" in eng.last_system
    assert SYSTEM_PROMPT in eng.last_system


def test_defaults_preserve_phase1_behavior():
    eng = FakeEngine([AssistantTurn(text="ok", tool_calls=[])])
    out = run_command("hi", Registry(), eng,
                      confirm=lambda c: True, on_step=_noop_step)
    assert out == "ok"
    assert len(eng.last_messages) == 1
    assert eng.last_system == SYSTEM_PROMPT
    assert "Known about the user" not in eng.last_system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_router_memory.py -v`
Expected: FAIL (`AttributeError: 'FakeEngine' object has no attribute 'last_system'`).

- [ ] **Step 3: Write minimal implementation**

Edit `jarvis/brain/engine.py` — update the `Engine` Protocol and `FakeEngine`:

```python
class Engine(Protocol):
    def complete(self, messages: list[Msg], tools: list[dict],
                 system: str = "") -> AssistantTurn:
        ...


class FakeEngine:
    """Returns pre-scripted turns; records the last call's inputs. Tests only."""
    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)
        self.last_messages: list[Msg] = []
        self.last_tools: list[dict] = []
        self.last_system: str = ""

    def complete(self, messages: list[Msg], tools: list[dict],
                 system: str = "") -> AssistantTurn:
        self.last_messages = messages
        self.last_tools = tools
        self.last_system = system
        return self._turns.pop(0)
```

Edit `jarvis/brain/claude_engine.py` — accept `system`, fall back to `SYSTEM_PROMPT`:

```python
    def complete(self, messages: list[Msg], tools: list[dict],
                 system: str = "") -> AssistantTurn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=system or SYSTEM_PROMPT,
            tools=tools,
            messages=_to_anthropic(messages),
        )
        return _parse(response)
```

Edit `jarvis/brain/router.py` — new params and system assembly:

```python
def run_command(text: str, registry: Registry, engine: Engine, *,
                confirm: ConfirmFn, on_step: StepFn, max_steps: int = 12,
                history: "list[Msg] | None" = None, memory_context: str = "") -> str:
    messages: list[Msg] = list(history or []) + [Msg(role="user", content=text)]
    tools = registry.schemas()
    system = SYSTEM_PROMPT
    if memory_context:
        system = f"{SYSTEM_PROMPT}\n\nKnown about the user:\n{memory_context}"

    for _ in range(max_steps):
        turn: AssistantTurn = engine.complete(messages, tools, system)
        messages.append(Msg(role="assistant", text=turn.text, tool_calls=turn.tool_calls))

        if turn.is_final:
            return turn.text or ""

        for call in turn.tool_calls:
            result = _run_one(call, registry, confirm)
            on_step(call, result)
            messages.append(Msg(role="tool", tool_call_id=call.id,
                                content=json.dumps(_serialize(result)), ok=result.ok))

    return "Stopped: reached max steps without finishing."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_router_memory.py tests/test_router.py tests/test_claude_engine.py tests/test_engine_types.py -v`
Expected: PASS (new memory router tests + all existing brain tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add jarvis/brain/engine.py jarvis/brain/claude_engine.py jarvis/brain/router.py tests/test_router_memory.py
git commit -m "feat: router history seeding + memory_context system injection"
```

---

### Task 5: Memory tools + registry wiring

**Files:**
- Create: `jarvis/memory/tools.py`
- Modify: `jarvis/tools/__init__.py` (`build_registry` accepts optional `mem`)
- Test: `tests/test_memory_tools.py`

**Interfaces:**
- Consumes: `MemoryService` (Task 3), `Registry`, `ToolResult`, `tool` from `jarvis.tools.base`.
- Produces: `jarvis.memory.tools.register(reg: Registry, mem: MemoryService) -> None` registering `remember_fact`, `recall`, `save_note`, `forget` (all `danger=False`).
  `build_registry(mem=None) -> Registry` — when `mem` is provided, also registers the memory tools.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_tools.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_tools.py -v`
Expected: FAIL (`TypeError: build_registry() takes 0 positional arguments` or `ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `jarvis/memory/tools.py`:

```python
"""Model-facing memory tools. Registered only when a MemoryService exists."""
import time

from jarvis.memory.service import MemoryService
from jarvis.tools.base import Registry, ToolResult, tool


def register(reg: Registry, mem: MemoryService) -> None:
    @tool(reg, name="remember_fact",
          description="Store a durable fact or preference about the user. Pass a "
                      "stable 'key' (e.g. 'editor') to overwrite a prior value.",
          schema={"type": "object",
                  "properties": {"text": {"type": "string"},
                                 "key": {"type": "string"}},
                  "required": ["text"]})
    def remember_fact(text, key=None):
        mem.add_fact(text, key, now=time.time())
        return ToolResult.ok({"remembered": text, "key": key})

    @tool(reg, name="recall",
          description="Search stored facts and notes for anything matching the query.",
          schema={"type": "object",
                  "properties": {"query": {"type": "string"}},
                  "required": ["query"]})
    def recall(query):
        q = query.lower()
        facts = [t for _, k, t in mem.list_facts()
                 if q in (t or "").lower() or q in (k or "").lower()]
        notes = mem.search_notes(query)
        return ToolResult.ok({"facts": facts, "notes": notes})

    @tool(reg, name="save_note",
          description="Save a named note. Reusing a key overwrites the note.",
          schema={"type": "object",
                  "properties": {"key": {"type": "string"},
                                 "text": {"type": "string"}},
                  "required": ["key", "text"]})
    def save_note(key, text):
        mem.add_note(key, text, now=time.time())
        return ToolResult.ok({"saved": key})

    @tool(reg, name="forget",
          description="Delete a stored fact (by key or numeric id) or a note (by key).",
          schema={"type": "object",
                  "properties": {"key_or_id": {"type": "string"}},
                  "required": ["key_or_id"]})
    def forget(key_or_id):
        removed = mem.forget_fact(key_or_id) or mem.forget_note(str(key_or_id))
        return ToolResult.ok({"forgotten": key_or_id, "removed": removed})
```

Edit `jarvis/tools/__init__.py`:

```python
"""Assemble the core tool registry."""
from jarvis.tools.base import Registry
from jarvis.tools import apps, windows, files, system, web


def build_registry(mem=None) -> Registry:
    reg = Registry()
    apps.register(reg)
    windows.register(reg)
    files.register(reg)
    system.register(reg)
    web.register(reg)
    if mem is not None:
        from jarvis.memory import tools as memory_tools
        memory_tools.register(reg, mem)
    return reg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_tools.py tests/test_tools_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jarvis/memory/tools.py jarvis/tools/__init__.py tests/test_memory_tools.py
git commit -m "feat: memory tools (remember_fact, recall, save_note, forget) + registry wiring"
```

---

### Task 6: Daemon wiring

**Files:**
- Modify: `jarvis/core/daemon.py`
- Test: `tests/test_daemon_memory.py`

**Interfaces:**
- Consumes: `Store`, `MemoryService`, `build_registry(mem)`, `run_command(... history=, memory_context=)`, `time`.
- Produces: `Daemon` constructs `self.mem = MemoryService(Store(settings.db_path), window_min=..., max_facts=...)`, builds the registry with it, and `_work` loads session context before the run and records the user turn, assistant turn, and command after.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daemon_memory.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_daemon_memory.py -v`
Expected: FAIL (`AttributeError: 'Daemon' object has no attribute 'mem'` raised inside `_work`).

- [ ] **Step 3: Write minimal implementation**

Edit `jarvis/core/daemon.py`. Add imports near the top:

```python
import threading
import time

from jarvis.memory.service import MemoryService
from jarvis.memory.store import Store
```

In `Daemon.__init__`, after `self.engine = ...`, replace the registry line:

```python
        self.mem = MemoryService(
            Store(self.settings.db_path),
            window_min=self.settings.session_window_min,
            max_facts=self.settings.max_facts_injected)
        self.registry = build_registry(self.mem)
```

Replace `_work` with the memory-wrapped version:

```python
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
```

(The existing `import threading` at the top may now be duplicated — keep a single `import threading`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_daemon_memory.py tests/test_daemon_confirm.py -v`
Expected: PASS (memory daemon tests + existing confirm regression test).

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/daemon.py tests/test_daemon_memory.py
git commit -m "feat: wire MemoryService into daemon; persist turns and commands per run"
```

---

### Task 7: Full-suite verification + docs

**Files:**
- Modify: `README.md`
- Test: full suite

**Interfaces:**
- Consumes: everything above.
- Produces: green full suite; README reflects memory.

- [ ] **Step 1: Run the full suite**

Run: `pytest`
Expected: PASS — all Phase-1 tests + the new memory tests (config, store, service, router-memory, tools, daemon-memory).

- [ ] **Step 2: Update README**

In `README.md`, update the test count line and add memory to capabilities. Replace the "What it can do (Phase 1)" paragraph's end and the architecture list to include:

```markdown
- `jarvis/memory` — sqlite-backed persistence: durable facts/prefs, time-window
  conversation continuity, command history, named notes (`store`, `service`, `tools`)
```

And add to the capabilities paragraph:

> It also remembers durable facts/preferences, keeps short-term conversation
> continuity (follow-ups within a 10-minute window), logs command history, and
> saves named notes — all stored locally in `%APPDATA%\jarvis\jarvis.db`.

Bump the test-count note (`(38 tests; ...)`) to the new total reported by `pytest`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README covers Phase 2a memory"
```

---

## Self-Review

**Spec coverage:**
- Durable facts/prefs → `facts` table (Task 2), `remember_fact`/`recall`/`forget` (Task 5), injected via `session_context` facts block (Task 3) + router (Task 4). ✓
- Conversation continuity (time-window) → `turns` table (Task 2), `session_context` windowing (Task 3), daemon record + history seeding (Tasks 6, 4). ✓
- Command history (append-only) → `commands` table (Task 2), `record_command` (Tasks 3, 6). ✓
- Named notes → `notes` table (Task 2), `save_note`/`recall`/`forget` (Task 5). ✓
- Brain integration (`history`, `memory_context`) → Task 4. ✓
- Daemon `_work` wrapping → Task 6. ✓
- Config (`session_window_min`, `data_dir`, `max_facts_injected`) → Task 1. ✓
- Error handling / graceful degradation → `MemoryService._safe` + try/except (Task 3, test `test_degrades_when_store_raises`). ✓
- Single connection + lock → Task 2 `Store._lock`. ✓
- Out-of-scope items (voice, local-router, extraction, mining, vector search) → not implemented. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type consistency:** `session_context(now) -> (str, list[Msg])` consistent across Tasks 3/4/6. `delete_fact(*, id=, key=)` (Task 2) matches `_fact_selector` kwargs (Task 3). `build_registry(mem=None)` consistent Tasks 5/6. `Engine.complete(messages, tools, system="")` consistent Tasks 4 (engine, claude_engine, router, FakeEngine). `ToolResult.ok(...)` constructor-style used per Phase-1 `base.py` pattern. ✓
