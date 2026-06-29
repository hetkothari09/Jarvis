# JARVIS Phase 1 (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows tray daemon that shows an always-on orb, opens a command palette on a global hotkey, sends the typed command to Claude, runs a tool-use loop over core desktop tools, and shows the result — with a confirm gate on dangerous tools.

**Architecture:** One background process (PySide6 + system tray) wires isolated modules over an in-process event bus. A neutral `Engine` interface lets the Brain router run a provider-agnostic tool-use loop (Claude in Phase 1). Tools are self-contained functions registered by a decorator; the registry exposes their JSON schemas to the engine. GUI (orb + palette) subscribes to bus events.

**Tech Stack:** Python 3.11+, PySide6 (Qt), anthropic SDK, pynput (global hotkey), pywin32 + psutil + pygetwindow + pyautogui (desktop tools), keyring (secrets), pydantic (config), pytest (tests).

---

## File Structure

```
pyproject.toml                 # project metadata, deps, pytest config
jarvis/
  __init__.py
  __main__.py                  # entry point: build + run daemon
  core/
    __init__.py
    bus.py                     # EventBus: in-proc pub/sub
    config.py                  # Settings (pydantic) + secret storage (keyring)
    daemon.py                  # wires modules, tray icon, lifecycle
  brain/
    __init__.py
    engine.py                  # neutral types: Msg, ToolCall, AssistantTurn, Engine protocol
    claude_engine.py           # ClaudeEngine: neutral <-> anthropic translation
    router.py                  # run_command: the tool-use loop
  tools/
    __init__.py
    base.py                    # ToolResult, @tool decorator, Registry
    apps.py                    # open_app, close_app
    windows.py                 # focus_window, arrange_window
    files.py                   # find_file, open_path
    system.py                  # set_volume, media_key, clipboard_get/set, run_shell
    web.py                     # web_answer
  gui/
    __init__.py
    theme.py                   # colors/constants for the futuristic look
    orb.py                     # always-on floating orb, reflects state
    palette.py                 # summoned command bar + results + confirm dialog
  input/
    __init__.py
    hotkey.py                  # global hotkey -> emits command request
tests/
  test_bus.py
  test_config.py
  test_tools_base.py
  test_tools_apps.py
  test_tools_windows.py
  test_tools_files.py
  test_tools_system.py
  test_router.py
  test_claude_engine.py
```

**Responsibilities:** `core/*` = process plumbing; `brain/*` = reasoning loop, no desktop knowledge; `tools/*` = all desktop side effects, no LLM knowledge; `gui/*` = presentation only, talks via bus; `input/*` = command sources.

---

### Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `jarvis/__init__.py` (empty)
- Create: package `__init__.py` files: `jarvis/core/__init__.py`, `jarvis/brain/__init__.py`, `jarvis/tools/__init__.py`, `jarvis/gui/__init__.py`, `jarvis/input/__init__.py` (all empty)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "jarvis"
version = "0.1.0"
description = "Personal desktop agent (Phase 1 MVP)"
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.7",
    "anthropic>=0.40",
    "pynput>=1.7",
    "psutil>=6.0",
    "pygetwindow>=0.0.9",
    "pyautogui>=0.9.54",
    "pywin32>=306; sys_platform == 'win32'",
    "keyring>=25",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
jarvis = "jarvis.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Create empty package files**

Create each `__init__.py` listed above as an empty file.

- [ ] **Step 3: Create venv and install**

Run (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
Expected: installs without error; `pytest --version` works.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml jarvis
git commit -m "chore: project scaffold for jarvis phase 1"
```

---

### Task 1: Event bus

**Files:**
- Create: `jarvis/core/bus.py`
- Test: `tests/test_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bus.py
from jarvis.core.bus import EventBus


def test_subscriber_receives_published_event():
    bus = EventBus()
    received = []
    bus.subscribe("command", lambda payload: received.append(payload))
    bus.publish("command", {"text": "hi"})
    assert received == [{"text": "hi"}]


def test_multiple_subscribers_each_get_event():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("evt", a.append)
    bus.subscribe("evt", b.append)
    bus.publish("evt", 1)
    assert a == [1] and b == [1]


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    got = []
    unsub = bus.subscribe("evt", got.append)
    unsub()
    bus.publish("evt", 1)
    assert got == []


def test_subscriber_error_does_not_break_others():
    bus = EventBus()
    good = []
    bus.subscribe("evt", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("evt", good.append)
    bus.publish("evt", 1)
    assert good == [1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.core.bus`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/core/bus.py
"""In-process publish/subscribe event bus. No threads, synchronous delivery."""
from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Callable[[Any], None]) -> Callable[[], None]:
        self._subs[topic].append(handler)

        def unsubscribe() -> None:
            if handler in self._subs[topic]:
                self._subs[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, payload: Any = None) -> None:
        for handler in list(self._subs[topic]):
            try:
                handler(payload)
            except Exception:
                # One bad subscriber must not break others or the publisher.
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_bus.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/bus.py tests/test_bus.py
git commit -m "feat: in-process event bus"
```

---

### Task 2: Config + secrets

**Files:**
- Create: `jarvis/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from jarvis.core.config import Settings, get_api_key, set_api_key


def test_defaults():
    s = Settings()
    assert s.hotkey == "<ctrl>+<space>"
    assert s.model == "claude-opus-4-8"
    assert s.max_steps == 12


def test_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_MAX_STEPS", "5")
    s = Settings()
    assert s.max_steps == 5


def test_api_key_roundtrip_via_keyring(monkeypatch):
    store = {}
    monkeypatch.setattr("jarvis.core.config.keyring.set_password",
                        lambda svc, user, pw: store.__setitem__((svc, user), pw))
    monkeypatch.setattr("jarvis.core.config.keyring.get_password",
                        lambda svc, user: store.get((svc, user)))
    set_api_key("sk-test")
    assert get_api_key() == "sk-test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.core.config`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/core/config.py
"""User settings (env-overridable) and secret storage (OS keyring)."""
import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE = "jarvis-desktop-agent"
_KEY_USER = "anthropic_api_key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_")

    hotkey: str = "<ctrl>+<space>"
    model: str = "claude-opus-4-8"
    max_steps: int = 12


def set_api_key(value: str) -> None:
    keyring.set_password(_SERVICE, _KEY_USER, value)


def get_api_key() -> str | None:
    return keyring.get_password(_SERVICE, _KEY_USER)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/core/config.py tests/test_config.py
git commit -m "feat: settings and keyring secret storage"
```

---

### Task 3: Tool base — ToolResult, @tool, Registry

**Files:**
- Create: `jarvis/tools/base.py`
- Test: `tests/test_tools_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_base.py
import pytest
from jarvis.tools.base import ToolResult, tool, Registry


def test_toolresult_helpers():
    ok = ToolResult.ok({"x": 1})
    err = ToolResult.err("nope")
    assert ok.ok is True and ok.data == {"x": 1} and ok.error is None
    assert err.ok is False and err.error == "nope" and err.data is None


def test_registry_collects_and_runs():
    reg = Registry()

    @tool(reg, name="add", description="add two ints",
          schema={"type": "object",
                  "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                  "required": ["a", "b"]})
    def add(a: int, b: int) -> ToolResult:
        return ToolResult.ok(a + b)

    assert reg.get("add").run(a=2, b=3).data == 5
    schemas = reg.schemas()
    assert schemas[0]["name"] == "add"
    assert schemas[0]["input_schema"]["required"] == ["a", "b"]


def test_danger_flag_defaults_false_and_can_be_set():
    reg = Registry()

    @tool(reg, name="safe", description="", schema={"type": "object", "properties": {}})
    def safe() -> ToolResult:
        return ToolResult.ok(None)

    @tool(reg, name="risky", description="", schema={"type": "object", "properties": {}},
          danger=True)
    def risky() -> ToolResult:
        return ToolResult.ok(None)

    assert reg.get("safe").danger is False
    assert reg.get("risky").danger is True


def test_unknown_tool_raises():
    reg = Registry()
    with pytest.raises(KeyError):
        reg.get("missing")


def test_run_wraps_exceptions_as_error_result():
    reg = Registry()

    @tool(reg, name="boom", description="", schema={"type": "object", "properties": {}})
    def boom() -> ToolResult:
        raise RuntimeError("kaboom")

    result = reg.get("boom").run()
    assert result.ok is False and "kaboom" in result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_base.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.tools.base`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/base.py
"""Tool contract: a uniform result type, a registration decorator, and a registry."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    @staticmethod
    def ok_(data: Any = None) -> "ToolResult":  # internal alias to avoid name clash
        return ToolResult(ok=True, data=data)

    @classmethod
    def err(cls, message: str) -> "ToolResult":
        return cls(ok=False, error=message)


# Public constructor for success (kept readable at call sites).
def _ok(data: Any = None) -> ToolResult:
    return ToolResult(ok=True, data=data)


ToolResult.ok = staticmethod(_ok)  # ToolResult.ok({...}) -> success result


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    danger: bool
    func: Callable[..., ToolResult]

    def run(self, **kwargs: Any) -> ToolResult:
        try:
            return self.func(**kwargs)
        except Exception as exc:  # tools never crash the loop
            return ToolResult.err(f"{type(exc).__name__}: {exc}")


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, t: Tool) -> None:
        self._tools[t.name] = t

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def schemas(self) -> list[dict]:
        # Anthropic tool format: name, description, input_schema.
        return [
            {"name": t.name, "description": t.description, "input_schema": t.schema}
            for t in self._tools.values()
        ]


def tool(registry: "Registry", *, name: str, description: str, schema: dict,
         danger: bool = False) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    def decorate(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        registry.add(Tool(name=name, description=description, schema=schema,
                          danger=danger, func=func))
        return func

    return decorate
```

> Note: `ToolResult.ok` is the success constructor (`ToolResult.ok({...})`) and instances also carry a boolean attribute set via the dataclass field `ok`. The dataclass field is read as `result.ok`; the classmethod-style constructor is `ToolResult.ok(data)`. To avoid confusion the implementation assigns the constructor after class definition. Keep this exactly as written.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_base.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/base.py tests/test_tools_base.py
git commit -m "feat: tool result, decorator, and registry"
```

---

### Task 4: App tools (open_app, close_app)

**Files:**
- Create: `jarvis/tools/apps.py`
- Test: `tests/test_tools_apps.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_apps.py
from jarvis.tools.base import Registry
from jarvis.tools import apps


def test_open_app_launches_via_startfile(monkeypatch):
    reg = Registry()
    calls = []
    monkeypatch.setattr(apps, "_launch", lambda target: calls.append(target))
    apps.register(reg)
    result = reg.get("open_app").run(name="notepad")
    assert result.ok is True
    assert calls == ["notepad"]


def test_close_app_kills_matching_processes(monkeypatch):
    reg = Registry()
    killed = []

    class FakeProc:
        def __init__(self, name):
            self.info = {"name": name}
        def kill(self):
            killed.append(self.info["name"])

    monkeypatch.setattr(apps, "_iter_processes",
                        lambda: [FakeProc("notepad.exe"), FakeProc("chrome.exe")])
    apps.register(reg)
    result = reg.get("close_app").run(name="notepad")
    assert result.ok is True
    assert killed == ["notepad.exe"]
    assert result.data["closed"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_apps.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.tools.apps`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/apps.py
"""Launch and close applications by name."""
import os

import psutil

from jarvis.tools.base import Registry, ToolResult, tool


def _launch(target: str) -> None:
    # os.startfile resolves PATH executables and registered app names on Windows.
    os.startfile(target)  # type: ignore[attr-defined]


def _iter_processes():
    return psutil.process_iter(["name"])


def register(reg: Registry) -> None:
    @tool(reg, name="open_app", description="Launch an application by name or path.",
          schema={"type": "object",
                  "properties": {"name": {"type": "string",
                                          "description": "App name or executable, e.g. 'notepad', 'chrome'"}},
                  "required": ["name"]})
    def open_app(name: str) -> ToolResult:
        _launch(name)
        return ToolResult.ok({"launched": name})

    @tool(reg, name="close_app",
          description="Close all running processes whose name contains the given text.",
          schema={"type": "object",
                  "properties": {"name": {"type": "string",
                                          "description": "Process name substring, e.g. 'notepad'"}},
                  "required": ["name"]},
          danger=True)
    def close_app(name: str) -> ToolResult:
        needle = name.lower().removesuffix(".exe")
        closed = 0
        for proc in _iter_processes():
            pname = (proc.info.get("name") or "").lower()
            if needle in pname:
                proc.kill()
                closed += 1
        return ToolResult.ok({"closed": closed})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_apps.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/apps.py tests/test_tools_apps.py
git commit -m "feat: app open/close tools"
```

---

### Task 5: Window tools (focus_window, arrange_window)

**Files:**
- Create: `jarvis/tools/windows.py`
- Test: `tests/test_tools_windows.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_windows.py
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
    # left half: moved to (0,0), resized to (960, 1080)
    assert win.box == (0, 0, 960, 1080)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_windows.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.tools.windows`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/windows.py
"""Focus and arrange top-level windows by title."""
import pygetwindow as gw

from jarvis.tools.base import Registry, ToolResult, tool


def _find_windows(title: str):
    return [w for w in gw.getAllWindows()
            if title.lower() in (w.title or "").lower() and w.title]


def _screen_size() -> tuple[int, int]:
    import ctypes
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def register(reg: Registry) -> None:
    @tool(reg, name="focus_window",
          description="Bring the first window whose title contains the text to the foreground.",
          schema={"type": "object",
                  "properties": {"title": {"type": "string"}},
                  "required": ["title"]})
    def focus_window(title: str) -> ToolResult:
        matches = _find_windows(title)
        if not matches:
            return ToolResult.err(f"no window matching '{title}'")
        matches[0].activate()
        return ToolResult.ok({"focused": matches[0].title})

    @tool(reg, name="arrange_window",
          description="Snap a window to a screen position.",
          schema={"type": "object",
                  "properties": {
                      "title": {"type": "string"},
                      "position": {"type": "string",
                                   "enum": ["left", "right", "maximize"]}},
                  "required": ["title", "position"]})
    def arrange_window(title: str, position: str) -> ToolResult:
        matches = _find_windows(title)
        if not matches:
            return ToolResult.err(f"no window matching '{title}'")
        win = matches[0]
        sw, sh = _screen_size()
        if position == "left":
            win.moveTo(0, 0); win.resizeTo(sw // 2, sh)
        elif position == "right":
            win.moveTo(sw // 2, 0); win.resizeTo(sw // 2, sh)
        elif position == "maximize":
            win.moveTo(0, 0); win.resizeTo(sw, sh)
        else:
            return ToolResult.err(f"unknown position '{position}'")
        return ToolResult.ok({"arranged": win.title, "position": position})
```

> Note: the test's `FakeWin.resizeTo` appends `(w, h)` to the move tuple, so after `moveTo(0,0)` then `resizeTo(960,1080)` the recorded `box` is `(0, 0, 960, 1080)`. Real `pygetwindow` calls are independent; the fake just records both calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_windows.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/windows.py tests/test_tools_windows.py
git commit -m "feat: window focus/arrange tools"
```

---

### Task 6: File tools (find_file, open_path)

**Files:**
- Create: `jarvis/tools/files.py`
- Test: `tests/test_tools_files.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_files.py
from pathlib import Path
from jarvis.tools.base import Registry
from jarvis.tools import files


def test_find_file_returns_matches(tmp_path, monkeypatch):
    (tmp_path / "resume.pdf").write_text("x")
    (tmp_path / "notes.txt").write_text("y")
    monkeypatch.setattr(files, "_search_roots", lambda: [tmp_path])
    reg = Registry()
    files.register(reg)
    result = reg.get("find_file").run(query="resume")
    assert result.ok is True
    names = [Path(p).name for p in result.data["matches"]]
    assert "resume.pdf" in names and "notes.txt" not in names


def test_find_file_limit(tmp_path, monkeypatch):
    for i in range(30):
        (tmp_path / f"doc{i}.txt").write_text("x")
    monkeypatch.setattr(files, "_search_roots", lambda: [tmp_path])
    reg = Registry()
    files.register(reg)
    result = reg.get("find_file").run(query="doc")
    assert len(result.data["matches"]) <= 20


def test_open_path_calls_startfile(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    opened = []
    monkeypatch.setattr(files, "_open", lambda p: opened.append(p))
    reg = Registry()
    files.register(reg)
    result = reg.get("open_path").run(path=str(f))
    assert result.ok is True and opened == [str(f)]


def test_open_path_missing_returns_error(monkeypatch):
    reg = Registry()
    files.register(reg)
    result = reg.get("open_path").run(path="C:\\does\\not\\exist.xyz")
    assert result.ok is False and "not found" in result.error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_files.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.tools.files`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/files.py
"""Find files under common user folders and open paths with the default handler."""
import os
from pathlib import Path

from jarvis.tools.base import Registry, ToolResult, tool

_MAX_MATCHES = 20


def _search_roots() -> list[Path]:
    home = Path.home()
    return [home / "Desktop", home / "Documents", home / "Downloads"]


def _open(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]


def register(reg: Registry) -> None:
    @tool(reg, name="find_file",
          description="Find files under Desktop/Documents/Downloads whose name contains the query.",
          schema={"type": "object",
                  "properties": {"query": {"type": "string"}},
                  "required": ["query"]})
    def find_file(query: str) -> ToolResult:
        needle = query.lower()
        matches: list[str] = []
        for root in _search_roots():
            if not root.exists():
                continue
            for dirpath, _dirs, names in os.walk(root):
                for n in names:
                    if needle in n.lower():
                        matches.append(str(Path(dirpath) / n))
                        if len(matches) >= _MAX_MATCHES:
                            return ToolResult.ok({"matches": matches})
        return ToolResult.ok({"matches": matches})

    @tool(reg, name="open_path",
          description="Open a file or folder with its default application.",
          schema={"type": "object",
                  "properties": {"path": {"type": "string"}},
                  "required": ["path"]})
    def open_path(path: str) -> ToolResult:
        if not Path(path).exists():
            return ToolResult.err(f"path not found: {path}")
        _open(path)
        return ToolResult.ok({"opened": path})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_files.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/files.py tests/test_tools_files.py
git commit -m "feat: find_file and open_path tools"
```

---

### Task 7: System tools (set_volume, media_key, clipboard, run_shell)

**Files:**
- Create: `jarvis/tools/system.py`
- Test: `tests/test_tools_system.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_system.py
from jarvis.tools.base import Registry
from jarvis.tools import system


def test_clipboard_roundtrip(monkeypatch):
    store = {"v": ""}
    monkeypatch.setattr(system, "_clip_set", lambda t: store.__setitem__("v", t))
    monkeypatch.setattr(system, "_clip_get", lambda: store["v"])
    reg = Registry()
    system.register(reg)
    assert reg.get("clipboard_set").run(text="hello").ok is True
    assert reg.get("clipboard_get").run().data["text"] == "hello"


def test_set_volume_clamps_and_calls(monkeypatch):
    seen = []
    monkeypatch.setattr(system, "_apply_volume", lambda pct: seen.append(pct))
    reg = Registry()
    system.register(reg)
    reg.get("set_volume").run(percent=150)
    reg.get("set_volume").run(percent=-5)
    assert seen == [100, 0]


def test_media_key_presses(monkeypatch):
    pressed = []
    monkeypatch.setattr(system, "_press", lambda key: pressed.append(key))
    reg = Registry()
    system.register(reg)
    result = reg.get("media_key").run(key="playpause")
    assert result.ok is True and pressed == ["playpause"]


def test_media_key_rejects_unknown():
    reg = Registry()
    system.register(reg)
    result = reg.get("media_key").run(key="explode")
    assert result.ok is False


def test_run_shell_is_dangerous_and_returns_output(monkeypatch):
    reg = Registry()
    monkeypatch.setattr(system, "_run", lambda cmd: ("hello\n", 0))
    system.register(reg)
    assert reg.get("run_shell").danger is True
    result = reg.get("run_shell").run(command="echo hello")
    assert result.ok is True and "hello" in result.data["stdout"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_system.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.tools.system`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/system.py
"""System controls: volume, media keys, clipboard, and a gated shell."""
import subprocess

from jarvis.tools.base import Registry, ToolResult, tool

_MEDIA_KEYS = {"playpause": "playpause", "next": "nexttrack",
               "prev": "prevtrack", "mute": "volumemute"}


def _clip_set(text: str) -> None:
    import pyperclip  # bundled with pyautogui
    pyperclip.copy(text)


def _clip_get() -> str:
    import pyperclip
    return pyperclip.paste()


def _apply_volume(percent: int) -> None:
    # Use the keyboard volume keys repeatedly via pyautogui as a portable approach.
    # Replaced by pycaw in a later phase; kept simple and mockable here.
    import pyautogui
    pyautogui.press("volumedown", presses=50)  # floor to 0
    pyautogui.press("volumeup", presses=percent // 2)  # each press ~2%


def _press(key: str) -> None:
    import pyautogui
    pyautogui.press(_MEDIA_KEYS[key])


def _run(command: str) -> tuple[str, int]:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    return (proc.stdout + proc.stderr), proc.returncode


def register(reg: Registry) -> None:
    @tool(reg, name="clipboard_set", description="Put text on the clipboard.",
          schema={"type": "object", "properties": {"text": {"type": "string"}},
                  "required": ["text"]})
    def clipboard_set(text: str) -> ToolResult:
        _clip_set(text)
        return ToolResult.ok({"set": True})

    @tool(reg, name="clipboard_get", description="Read the current clipboard text.",
          schema={"type": "object", "properties": {}})
    def clipboard_get() -> ToolResult:
        return ToolResult.ok({"text": _clip_get()})

    @tool(reg, name="set_volume", description="Set system volume to a percent (0-100).",
          schema={"type": "object",
                  "properties": {"percent": {"type": "integer"}},
                  "required": ["percent"]})
    def set_volume(percent: int) -> ToolResult:
        pct = max(0, min(100, percent))
        _apply_volume(pct)
        return ToolResult.ok({"volume": pct})

    @tool(reg, name="media_key",
          description="Send a media key: playpause, next, prev, mute.",
          schema={"type": "object",
                  "properties": {"key": {"type": "string",
                                         "enum": list(_MEDIA_KEYS.keys())}},
                  "required": ["key"]})
    def media_key(key: str) -> ToolResult:
        if key not in _MEDIA_KEYS:
            return ToolResult.err(f"unknown media key '{key}'")
        _press(key)
        return ToolResult.ok({"pressed": key})

    @tool(reg, name="run_shell",
          description="Run a shell command and return its output. Use only when explicitly needed.",
          schema={"type": "object",
                  "properties": {"command": {"type": "string"}},
                  "required": ["command"]},
          danger=True)
    def run_shell(command: str) -> ToolResult:
        out, code = _run(command)
        return ToolResult.ok({"stdout": out, "exit_code": code})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_system.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/system.py tests/test_tools_system.py
git commit -m "feat: system tools (volume, media, clipboard, gated shell)"
```

---

### Task 8: Web tool (web_answer) + tools package assembly

**Files:**
- Create: `jarvis/tools/web.py`
- Modify: `jarvis/tools/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools_web.py
from jarvis.tools.base import Registry
from jarvis.tools import web, build_registry


def test_web_answer_marks_question_for_brain(monkeypatch):
    reg = Registry()
    web.register(reg)
    result = reg.get("web_answer").run(question="weather in Tokyo")
    # web_answer is a marker tool: it returns the question so the Brain answers
    # it directly from its own knowledge/tools. (Real web fetch is Phase 2.)
    assert result.ok is True
    assert result.data["question"] == "weather in Tokyo"


def test_build_registry_has_core_tools():
    reg = build_registry()
    names = {s["name"] for s in reg.schemas()}
    assert {"open_app", "close_app", "focus_window", "arrange_window",
            "find_file", "open_path", "set_volume", "media_key",
            "clipboard_get", "clipboard_set", "run_shell", "web_answer"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools_web.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/tools/web.py
"""Lightweight web/answer marker tool.

Phase 1 keeps this minimal: it echoes the question back so the Brain answers
from its own knowledge. Phase 2 replaces the body with a real fetch/search.
"""
from jarvis.tools.base import Registry, ToolResult, tool


def register(reg: Registry) -> None:
    @tool(reg, name="web_answer",
          description="Answer a general-knowledge or web-style question.",
          schema={"type": "object",
                  "properties": {"question": {"type": "string"}},
                  "required": ["question"]})
    def web_answer(question: str) -> ToolResult:
        return ToolResult.ok({"question": question})
```

```python
# jarvis/tools/__init__.py
"""Assemble the core tool registry."""
from jarvis.tools.base import Registry
from jarvis.tools import apps, windows, files, system, web


def build_registry() -> Registry:
    reg = Registry()
    apps.register(reg)
    windows.register(reg)
    files.register(reg)
    system.register(reg)
    web.register(reg)
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tools_web.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/tools/web.py jarvis/tools/__init__.py tests/test_tools_web.py
git commit -m "feat: web_answer tool and registry assembly"
```

---

### Task 9: Brain neutral types + Engine protocol + FakeEngine

**Files:**
- Create: `jarvis/brain/engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_types.py
from jarvis.brain.engine import Msg, ToolCall, AssistantTurn, FakeEngine


def test_assistant_turn_final_vs_tools():
    final = AssistantTurn(text="done", tool_calls=[])
    acting = AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="open_app",
                                                           args={"name": "notepad"})])
    assert final.is_final is True
    assert acting.is_final is False


def test_fake_engine_returns_scripted_turns_in_order():
    turns = [
        AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="x", args={})]),
        AssistantTurn(text="all done", tool_calls=[]),
    ]
    engine = FakeEngine(turns)
    assert engine.complete([Msg(role="user", content="hi")], []).tool_calls[0].name == "x"
    assert engine.complete([], []).text == "all done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine_types.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.brain.engine`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/brain/engine.py
"""Provider-neutral conversation types and the Engine interface.

The router speaks only these types. Each concrete engine (Claude, later Ollama)
translates them to/from its provider format. FakeEngine is used in tests.
"""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Msg:
    role: str                       # "user" | "assistant" | "tool"
    content: str | None = None      # text for user/tool messages
    text: str | None = None         # assistant free text
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None # for role == "tool"
    ok: bool = True                 # for role == "tool"


@dataclass
class AssistantTurn:
    text: str | None
    tool_calls: list[ToolCall]

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class Engine(Protocol):
    def complete(self, messages: list[Msg], tools: list[dict]) -> AssistantTurn:
        ...


class FakeEngine:
    """Returns pre-scripted turns; ignores inputs. For tests only."""
    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)

    def complete(self, messages: list[Msg], tools: list[dict]) -> AssistantTurn:
        return self._turns.pop(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_engine_types.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/brain/engine.py tests/test_engine_types.py
git commit -m "feat: neutral brain types and fake engine"
```

---

### Task 10: Router (the tool-use loop)

**Files:**
- Create: `jarvis/brain/router.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
from jarvis.brain.engine import AssistantTurn, ToolCall, FakeEngine
from jarvis.brain.router import run_command
from jarvis.tools.base import Registry, ToolResult, tool


def _registry_with_echo():
    reg = Registry()

    @tool(reg, name="echo", description="echo", danger=False,
          schema={"type": "object", "properties": {"v": {"type": "string"}},
                  "required": ["v"]})
    def echo(v: str) -> ToolResult:
        return ToolResult.ok({"v": v})

    @tool(reg, name="wipe", description="wipe", danger=True,
          schema={"type": "object", "properties": {}})
    def wipe() -> ToolResult:
        return ToolResult.ok({"wiped": True})

    return reg


def test_runs_tools_then_returns_final_text():
    reg = _registry_with_echo()
    engine = FakeEngine([
        AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="echo", args={"v": "hi"})]),
        AssistantTurn(text="done", tool_calls=[]),
    ])
    steps = []
    out = run_command("say hi", reg, engine, confirm=lambda c: True,
                      on_step=lambda call, res: steps.append((call.name, res.ok)),
                      max_steps=12)
    assert out == "done"
    assert steps == [("echo", True)]


def test_max_steps_cap_stops_loop():
    reg = _registry_with_echo()
    # Always asks to call a tool, never finalizes.
    looping = [AssistantTurn(text=None,
                             tool_calls=[ToolCall(id=str(i), name="echo", args={"v": "x"})])
               for i in range(50)]
    engine = FakeEngine(looping)
    out = run_command("loop", reg, engine, confirm=lambda c: True,
                      on_step=lambda *_: None, max_steps=3)
    assert "max steps" in out.lower()


def test_danger_tool_declined_returns_error_result_not_run():
    reg = _registry_with_echo()
    engine = FakeEngine([
        AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="wipe", args={})]),
        AssistantTurn(text="ok", tool_calls=[]),
    ])
    seen = []
    run_command("wipe", reg, engine, confirm=lambda c: False,
                on_step=lambda call, res: seen.append(res), max_steps=12)
    assert seen[0].ok is False and "declined" in seen[0].error.lower()


def test_unknown_tool_yields_error_result():
    reg = _registry_with_echo()
    engine = FakeEngine([
        AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="ghost", args={})]),
        AssistantTurn(text="ok", tool_calls=[]),
    ])
    seen = []
    run_command("x", reg, engine, confirm=lambda c: True,
                on_step=lambda call, res: seen.append(res), max_steps=12)
    assert seen[0].ok is False and "unknown tool" in seen[0].error.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.brain.router`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/brain/router.py
"""The provider-agnostic tool-use loop."""
import json
from typing import Callable

from jarvis.brain.engine import AssistantTurn, Engine, Msg, ToolCall
from jarvis.tools.base import Registry, ToolResult

SYSTEM_PROMPT = (
    "You are JARVIS, a desktop assistant on Windows. "
    "Use the provided tools to accomplish the user's request. "
    "Prefer the most direct tool. When the task is complete, reply with a short "
    "confirmation of what you did. If a tool returns an error, adapt or explain."
)

ConfirmFn = Callable[[ToolCall], bool]
StepFn = Callable[[ToolCall, ToolResult], None]


def run_command(text: str, registry: Registry, engine: Engine, *,
                confirm: ConfirmFn, on_step: StepFn, max_steps: int = 12) -> str:
    messages: list[Msg] = [Msg(role="user", content=text)]
    tools = registry.schemas()

    for _ in range(max_steps):
        turn: AssistantTurn = engine.complete(messages, tools)
        messages.append(Msg(role="assistant", text=turn.text, tool_calls=turn.tool_calls))

        if turn.is_final:
            return turn.text or ""

        for call in turn.tool_calls:
            result = _run_one(call, registry, confirm)
            on_step(call, result)
            messages.append(Msg(role="tool", tool_call_id=call.id,
                                content=json.dumps(_serialize(result)), ok=result.ok))

    return "Stopped: reached max steps without finishing."


def _run_one(call: ToolCall, registry: Registry, confirm: ConfirmFn) -> ToolResult:
    try:
        tool = registry.get(call.name)
    except KeyError:
        return ToolResult.err(f"unknown tool '{call.name}'")
    if tool.danger and not confirm(call):
        return ToolResult.err("declined by user")
    return tool.run(**call.args)


def _serialize(result: ToolResult) -> dict:
    return {"ok": result.ok, "data": result.data, "error": result.error}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_router.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/brain/router.py tests/test_router.py
git commit -m "feat: provider-agnostic tool-use loop"
```

---

### Task 11: Claude engine (neutral <-> anthropic translation)

**Files:**
- Create: `jarvis/brain/claude_engine.py`
- Test: `tests/test_claude_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_claude_engine.py
from jarvis.brain.engine import Msg, ToolCall
from jarvis.brain.claude_engine import ClaudeEngine


class FakeBlock:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, blocks):
        self.content = blocks


class FakeMessages:
    def __init__(self, response, captured):
        self._response = response
        self._captured = captured
    def create(self, **kwargs):
        self._captured.update(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response, captured):
        self.messages = FakeMessages(response, captured)


def test_parses_tool_use_and_text_blocks():
    captured = {}
    response = FakeResponse([
        FakeBlock("text", text="working on it"),
        FakeBlock("tool_use", id="abc", name="open_app", input={"name": "notepad"}),
    ])
    engine = ClaudeEngine(client=FakeClient(response, captured), model="claude-opus-4-8")
    turn = engine.complete([Msg(role="user", content="open notepad")],
                           [{"name": "open_app", "description": "d", "input_schema": {}}])
    assert turn.text == "working on it"
    assert turn.tool_calls == [ToolCall(id="abc", name="open_app", args={"name": "notepad"})]
    # the system prompt and tools were forwarded
    assert captured["model"] == "claude-opus-4-8"
    assert captured["tools"][0]["name"] == "open_app"


def test_translates_tool_result_message():
    captured = {}
    response = FakeResponse([FakeBlock("text", text="done")])
    engine = ClaudeEngine(client=FakeClient(response, captured), model="m")
    messages = [
        Msg(role="user", content="hi"),
        Msg(role="assistant", text=None,
            tool_calls=[ToolCall(id="t1", name="open_app", args={"name": "x"})]),
        Msg(role="tool", tool_call_id="t1", content='{"ok": true}', ok=True),
    ]
    engine.complete(messages, [])
    sent = captured["messages"]
    # user, assistant(tool_use), user(tool_result)
    assert sent[0]["role"] == "user"
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0]["type"] == "tool_use"
    assert sent[2]["role"] == "user"
    assert sent[2]["content"][0]["type"] == "tool_result"
    assert sent[2]["content"][0]["tool_use_id"] == "t1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_claude_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.brain.claude_engine`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/brain/claude_engine.py
"""Claude implementation of the Engine protocol.

Converts neutral Msg lists to the Anthropic Messages API format on each call
(stateless), and parses the response content blocks back into an AssistantTurn.
"""
from typing import Any

from jarvis.brain.engine import AssistantTurn, Msg, ToolCall
from jarvis.brain.router import SYSTEM_PROMPT

_MAX_TOKENS = 1024


class ClaudeEngine:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, messages: list[Msg], tools: list[dict]) -> AssistantTurn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=_to_anthropic(messages),
        )
        return _parse(response)


def _to_anthropic(messages: list[Msg]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "user":
            out.append({"role": "user", "content": m.content or ""})
        elif m.role == "assistant":
            blocks: list[dict] = []
            if m.text:
                blocks.append({"type": "text", "text": m.text})
            for call in m.tool_calls:
                blocks.append({"type": "tool_use", "id": call.id,
                               "name": call.name, "input": call.args})
            out.append({"role": "assistant", "content": blocks})
        elif m.role == "tool":
            out.append({"role": "user",
                        "content": [{"type": "tool_result",
                                     "tool_use_id": m.tool_call_id,
                                     "content": m.content or ""}]})
    return out


def _parse(response: Any) -> AssistantTurn:
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, args=dict(block.input)))
    text = "".join(text_parts) if text_parts else None
    return AssistantTurn(text=text, tool_calls=calls)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_claude_engine.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/brain/claude_engine.py tests/test_claude_engine.py
git commit -m "feat: Claude engine with neutral<->anthropic translation"
```

---

### Task 12: GUI theme + orb

**Files:**
- Create: `jarvis/gui/theme.py`
- Create: `jarvis/gui/orb.py`

> GUI is verified manually (Qt rendering). Tests here are limited to non-visual state logic.

- [ ] **Step 1: Write the failing test (state logic only)**

```python
# tests/test_orb_state.py
from jarvis.gui.orb import orb_color
from jarvis.gui.theme import IDLE, BUSY, ERROR


def test_orb_color_maps_state():
    assert orb_color("idle") == IDLE
    assert orb_color("busy") == BUSY
    assert orb_color("error") == ERROR
    assert orb_color("anything-else") == IDLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orb_state.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.gui.orb`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/gui/theme.py
"""Futuristic theme tokens."""
BG = "#0b0f16"
PANEL = "#11171f"
ACCENT = "#5fd6ff"
TEXT = "#e6f1ff"
MUTED = "#8aa0b6"

IDLE = "#3aa6e0"   # calm blue
BUSY = "#5fd6ff"   # bright cyan (pulsing)
ERROR = "#ff5f6d"  # red
```

```python
# jarvis/gui/orb.py
"""Always-on floating orb. Frameless, translucent, click-through-free.

The orb reflects the agent state via color. Visual rendering is verified
manually; orb_color() holds the testable mapping.
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from jarvis.gui.theme import IDLE, BUSY, ERROR

_DIAMETER = 64


def orb_color(state: str) -> str:
    return {"idle": IDLE, "busy": BUSY, "error": ERROR}.get(state, IDLE)


class Orb(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._state = "idle"
        self._pulse = 0.0
        self.setFixedSize(_DIAMETER, _DIAMETER)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._place_bottom_right()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def _place_bottom_right(self) -> None:
        screen = self.screen().availableGeometry()
        self.move(screen.right() - _DIAMETER - 24, screen.bottom() - _DIAMETER - 24)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.06) % 1.0
        if self._state != "idle":
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        radius = _DIAMETER / 2
        grad = QRadialGradient(center, radius)
        base = QColor(orb_color(self._state))
        glow = QColor(base)
        glow.setAlpha(90 if self._state == "idle" else int(120 + 100 * self._pulse))
        grad.setColorAt(0.0, base)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(self.rect())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_orb_state.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/gui/theme.py jarvis/gui/orb.py tests/test_orb_state.py
git commit -m "feat: theme tokens and floating orb widget"
```

---

### Task 13: GUI palette + confirm dialog

**Files:**
- Create: `jarvis/gui/palette.py`

> Manual-verified Qt widget. No automated test (pure presentation + signal wiring).

- [ ] **Step 1: Write the implementation**

```python
# jarvis/gui/palette.py
"""Summoned command palette: a frameless centered input + result area.

Emits `submitted(str)` when the user presses Enter. Shows step lines and the
final result. `confirm(text)` shows a modal yes/no for dangerous tools.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QLabel, QLineEdit, QMessageBox,
                               QVBoxLayout, QWidget)

from jarvis.gui.theme import ACCENT, BG, MUTED, PANEL, TEXT


class Palette(QWidget):
    submitted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(680)

        card = QFrame(self)
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask JARVIS…   (Esc to dismiss)")
        self._input.returnPressed.connect(self._on_return)
        layout.addWidget(self._input)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setObjectName("status")
        layout.addWidget(self._status)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        self.setStyleSheet(f"""
            #card {{ background: {PANEL}; border: 1px solid {ACCENT};
                     border-radius: 14px; }}
            QLineEdit {{ background: {BG}; color: {TEXT}; border: 1px solid #1e2a38;
                         border-radius: 10px; padding: 12px 14px; font-size: 16px; }}
            #status {{ color: {MUTED}; font-size: 13px; }}
        """)

    # --- public API used by the daemon ---

    def summon(self) -> None:
        self._input.clear()
        self._status.setText("")
        self._center_top()
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def show_step(self, line: str) -> None:
        prev = self._status.text()
        self._status.setText((prev + "\n" + line).strip())

    def show_result(self, text: str) -> None:
        self._status.setText(text)

    def confirm(self, message: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Confirm action")
        box.setText(message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    # --- internals ---

    def _on_return(self) -> None:
        text = self._input.text().strip()
        if text:
            self.submitted.emit(text)

    def _center_top(self) -> None:
        screen = self.screen().availableGeometry()
        self.adjustSize()
        x = screen.center().x() - self.width() // 2
        y = screen.top() + int(screen.height() * 0.22)
        self.move(x, y)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
```

- [ ] **Step 2: Manual smoke check**

Add a temporary scratch script `scratch_palette.py`:
```python
from PySide6.QtWidgets import QApplication
from jarvis.gui.palette import Palette
app = QApplication([])
p = Palette()
p.submitted.connect(lambda t: p.show_result(f"you said: {t}"))
p.summon()
app.exec()
```
Run: `python scratch_palette.py`
Expected: frameless cyan-bordered bar near top-center; typing + Enter shows "you said: …"; Esc hides. Delete the scratch file after.

- [ ] **Step 3: Commit**

```bash
git add jarvis/gui/palette.py
git commit -m "feat: command palette widget with confirm dialog"
```

---

### Task 14: Global hotkey listener

**Files:**
- Create: `jarvis/input/hotkey.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkey.py
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
    # Simulate the OS firing the bound hotkey.
    captured["mapping"]["<ctrl>+<space>"]()
    assert fired == [True]
    assert captured["started"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hotkey.py -v`
Expected: FAIL — `ModuleNotFoundError: jarvis.input.hotkey`

- [ ] **Step 3: Write minimal implementation**

```python
# jarvis/input/hotkey.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hotkey.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add jarvis/input/hotkey.py tests/test_hotkey.py
git commit -m "feat: global hotkey listener"
```

---

### Task 15: Daemon wiring + tray + entry point

**Files:**
- Create: `jarvis/core/daemon.py`
- Create: `jarvis/__main__.py`

> Wires everything: tray icon, orb, palette, hotkey, brain. The Brain runs on a
> worker thread so the UI never blocks; results are marshaled back to the Qt thread
> via signals. Verified manually end-to-end.

- [ ] **Step 1: Write the daemon**

```python
# jarvis/core/daemon.py
"""Compose all modules into a running tray application."""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from anthropic import Anthropic

from jarvis.brain.claude_engine import ClaudeEngine
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
        self.registry = build_registry()

        self.orb = Orb()
        self.palette = Palette()
        self.bridge = _Bridge()

        self.bridge.step.connect(self.palette.show_step)
        self.bridge.done.connect(self.palette.show_result)
        self.bridge.state.connect(self.orb.set_state)
        self.bridge.summon.connect(self.palette.summon)
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

        def on_step(call: ToolCall, result: ToolResult) -> None:
            status = "ok" if result.ok else f"error: {result.error}"
            self.bridge.step.emit(f"› {call.name} — {status}")

        def confirm(call: ToolCall) -> bool:
            # Confirm must happen on the UI thread; use a blocking invoke.
            return _confirm_on_ui(self.palette, call)

        try:
            answer = run_command(text, self.registry, self.engine,
                                 confirm=confirm, on_step=on_step,
                                 max_steps=self.settings.max_steps)
            self.bridge.done.emit(answer)
            self.bridge.state.emit("idle")
        except Exception as exc:  # network/engine failure
            self.bridge.done.emit(f"Error: {exc}")
            self.bridge.state.emit("error")

    def run(self) -> int:
        self.orb.show()
        self.hotkey.start()
        return self.app.exec()


def _confirm_on_ui(palette: Palette, call: ToolCall) -> bool:
    """Run the modal confirm on the Qt thread and block the worker for the answer."""
    from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_RETURN_ARG, Q_ARG  # noqa
    result: dict = {}
    done = threading.Event()

    def ask() -> None:
        result["ok"] = palette.confirm(
            f"JARVIS wants to run a sensitive action:\n\n{call.name}({call.args})\n\nAllow?")
        done.set()

    # Schedule on the UI thread.
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, ask)
    done.wait()
    return bool(result.get("ok"))
```

```python
# jarvis/__main__.py
"""Entry point: run the JARVIS daemon."""
from jarvis.core.daemon import Daemon


def main() -> int:
    return Daemon().run()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Set the API key (one-time)**

Run (PowerShell, in the venv):
```powershell
python -c "from jarvis.core.config import set_api_key; set_api_key('sk-ant-REPLACE')"
```
Expected: no output, key stored in Windows Credential Manager.

- [ ] **Step 3: Full manual smoke test**

Run: `python -m jarvis`
Expected and verify each:
1. Tray icon (cyan dot) appears; orb glows bottom-right.
2. Press `Ctrl+Space` → palette appears top-center.
3. Type `open notepad` → Enter. Orb pulses; step line `› open_app — ok`; Notepad opens; result text shows.
4. Type `set volume to 30` → volume changes; confirm not required (not dangerous).
5. Type `delete everything on my desktop with a shell command` → a confirm dialog appears before `run_shell`; clicking No aborts safely.
6. Type `snap notepad to the left` → Notepad fills left half.
7. Esc hides palette; tray → Quit exits cleanly.

- [ ] **Step 4: Commit**

```bash
git add jarvis/core/daemon.py jarvis/__main__.py
git commit -m "feat: daemon wiring, tray, and entry point"
```

---

### Task 16: Full test sweep + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the whole suite**

Run: `pytest`
Expected: all tests pass (bus, config, tools_base, tools_apps, tools_windows, tools_files, tools_system, tools_web, engine_types, router, claude_engine, orb_state, hotkey).

- [ ] **Step 2: Write `README.md`**

```markdown
# JARVIS — Personal Desktop Agent (Phase 1 MVP)

Always-on Windows tray agent. Press `Ctrl+Space`, type a command, and JARVIS uses
Claude + desktop tools to do it.

## Setup
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -c "from jarvis.core.config import set_api_key; set_api_key('sk-ant-...')"

## Run
    python -m jarvis

## Test
    pytest

## What it can do (Phase 1)
Open/close apps, focus/arrange windows, find/open files, set volume, media keys,
clipboard, gated shell, and general answers. Dangerous actions ask first.

## Next phases
- Phase 2: voice (wake word + STT + TTS), local model router, memory.
- Phase 3: workflows/macros, scheduling, full-HUD summon mode.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: phase 1 README"
```

---

## Self-Review

**Spec coverage:**
- Tray daemon + lifecycle → Task 15. ✓
- Event bus → Task 1 (built; daemon uses Qt signals as the live bus between worker and UI, with `EventBus` available for non-UI module decoupling). ✓
- Config + keyring secrets → Task 2. ✓
- Tool plugin contract + registry → Task 3; core tools → Tasks 4–8. ✓
- Engine-agnostic brain + tool-use loop + max-steps cap → Tasks 9–10. ✓
- Claude engine → Task 11. ✓
- Command palette + confirm gate → Task 13; orb → Task 12. ✓
- Global hotkey → Task 14. ✓
- Dangerous-action confirmation → Task 7 (`danger=True`), enforced in Task 10 router + Task 15 UI confirm. ✓
- Error handling (tool errors as results, engine failure surfaced, daemon survives) → Tasks 3, 10, 15. ✓
- Testing strategy (unit tools, fake-engine router, translation, manual smoke) → Tasks 1–16. ✓

**Deferred by design (Phase 2/3, not gaps):** voice, local engine, TTS, memory/sqlite, workflows. The `EventBus` from Task 1 is intentionally available for those modules even though Phase 1's live path uses Qt signals for thread-safe UI marshaling.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `ToolResult` (ok/data/error), `ToolCall(id,name,args)`, `AssistantTurn(text,tool_calls,is_final)`, `Msg(role,content,text,tool_calls,tool_call_id,ok)`, `run_command(text, registry, engine, *, confirm, on_step, max_steps)`, `register(reg)` per tool module, `build_registry()` — names match across Tasks 3–16.

---

## Notes for the implementer

- **Run tests on every task.** Tools are mocked — no real apps move during `pytest`.
- **GUI/daemon are manual-verified** (Tasks 13, 15). Qt rendering and global hotkeys can't be unit-tested meaningfully; follow the smoke checklists exactly.
- **Thread safety:** the Brain runs off the UI thread; all UI updates go through `_Bridge` signals. Don't touch Qt widgets from `_work`.
- **`ToolResult.ok`** is both the boolean field (`result.ok`) and the success constructor (`ToolResult.ok(data)`) — keep `base.py` exactly as written in Task 3.
