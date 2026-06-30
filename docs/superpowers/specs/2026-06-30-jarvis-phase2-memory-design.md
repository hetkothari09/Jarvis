# JARVIS Phase 2a — Memory & State Design

**Date:** 2026-06-30
**Status:** Approved
**Builds on:** Phase 1 MVP (`docs/superpowers/specs/2026-06-29-jarvis-desktop-agent-design.md`)

## Context

Phase 1 shipped an always-on Windows tray agent: hotkey-summoned command palette,
floating orb, provider-agnostic tool-use brain (Claude), desktop tool plugins, and
GUI-gated dangerous actions. The brain is **stateless** — every `run_command` starts
from a fresh `[user]` message list with a static `SYSTEM_PROMPT`, so nothing carries
between commands.

Phase 2 (per the approved overall design) covers three independent subsystems: voice,
local-model routing, and memory/state. These are loosely coupled and each warrants its
own spec→plan→build cycle. **This spec covers memory/state only** (Phase 2a). Voice and
local-router are deferred to their own specs.

## Goal

Give JARVIS persistent memory so it can:
- hold **durable facts/preferences** (name, default editor, projects folder, habits the
  user states) and inject them as context;
- support **conversation continuity** — follow-ups like "do that again" / "close that
  window" resolve against recent turns;
- keep a **command history** (append-only) for recall and as raw data a future
  habit-miner can analyze;
- store **named notes** the user explicitly saves and recalls.

Auto-extraction of facts and habit/routine *mining* are explicitly out of scope here
(YAGNI). The command-history table accumulates the data a later miner would read; stated
habits land in durable facts via the `remember_fact` tool.

## Architecture

New package `jarvis/memory/`, three units with clear boundaries:

### `store.py` — sqlite wrapper
Thin CRUD layer. Owns the connection and schema init; no business logic. Schema
(idempotent `CREATE TABLE IF NOT EXISTS`):

- `facts(id INTEGER PK, key TEXT, text TEXT, created_at REAL)` — durable facts/prefs.
  `key` nullable; when set, insert is an **upsert** (re-stating "default editor"
  overwrites the prior value).
- `notes(id INTEGER PK, key TEXT UNIQUE, text TEXT, created_at REAL, updated_at REAL)`
  — named snippets; upsert by `key`.
- `turns(id INTEGER PK, ts REAL, role TEXT, text TEXT)` — conversation log; source for
  time-window continuity.
- `commands(id INTEGER PK, ts REAL, text TEXT, ok INTEGER, summary TEXT)` — append-only
  history + audit.

A single connection is guarded by a `threading.Lock` (daemon spawns worker threads).

### `service.py` — `MemoryService`
The only class daemon and tools touch. Hides sqlite, windowing, and rendering.

```
session_context(now: float) -> tuple[str, list[Msg]]
    # facts_block: facts rendered as lines ("- default editor: VS Code"),
    #              capped at max_facts_injected (default 100), most-recent first.
    # turns:       turns with ts >= now - window_min*60, oldest first, as Msg(role, text).
record_turn(role: str, text: str, ts: float) -> None
record_command(text: str, ok: bool, summary: str, ts: float) -> None
add_fact(text: str, key: str | None = None) -> None
list_facts() -> list                      # (id, key, text)
forget_fact(id_or_key) -> bool
add_note(key: str, text: str) -> None      # upsert
get_note(key: str) -> str | None
search_notes(query: str) -> list           # substring match on key+text
```

All store access is wrapped: on any sqlite error the service **logs and degrades** —
`session_context` returns `("", [])`, writes become no-ops — so a memory failure never
kills a command. The orb surfaces an error state once; the run continues.

### `tools.py` — model-facing tools
Registers memory tools into the existing `Registry`, extending the Phase-1
`register(reg)` pattern to `register(reg, mem)` (the `MemoryService` is captured in the
tool closures).

| tool | args | danger | effect |
|------|------|--------|--------|
| `remember_fact` | `text`, `key?` | no | durable fact/pref; `key` set ⇒ upsert |
| `recall` | `query` | no | search facts + notes, return matches |
| `save_note` | `key`, `text` | no | named snippet, upsert by key |
| `forget` | `key_or_id` | no | delete a fact/note |

`forget` is **not** danger-gated: it touches only the user's own memory (not the system)
and is reversible by re-adding.

### Brain integration
`run_command` gains two optional, backward-compatible params:

```
run_command(text, registry, engine, *, confirm, on_step, max_steps=12,
            history: list[Msg] | None = None, memory_context: str = "")
```

- `history` — turns prepended before the user message (seed continuity).
- `memory_context` — appended to `SYSTEM_PROMPT` as
  `"\n\nKnown about the user:\n{memory_context}"` when non-empty.

The router stays stateless. The **daemon** owns the `MemoryService` and supplies/persists
context around each run.

### Daemon `_work` change
```
now = time.time()
facts, turns = self.mem.session_context(now)
self.mem.record_turn("user", text, now)
answer = run_command(text, self.registry, self.engine,
                     confirm=confirm, on_step=on_step,
                     max_steps=self.settings.max_steps,
                     history=turns, memory_context=facts)
self.mem.record_turn("assistant", answer, time.time())
self.mem.record_command(text, ok=<not errored>, summary=answer[:200], ts=now)
```
The registry is built with memory tools registered (`build_registry(mem)`).

### Config additions (`Settings`)
- `session_window_min: int = 10`
- `data_dir: Path = %APPDATA%\jarvis` (DB at `data_dir / "jarvis.db"`, created first run)
- `max_facts_injected: int = 100`

## Data flow (per command)

1. Hotkey/palette → daemon `_work(text)` at `now`.
2. `mem.session_context(now)` → facts block + turns within the 10-min window.
3. `record_turn("user", text, now)`.
4. `run_command(... history=turns, memory_context=facts)`; SYSTEM_PROMPT gains the facts
   block, turns seeded before the user msg. Model may call the memory tools mid-run;
   writes go straight through `MemoryService`.
5. On finish: `record_turn("assistant", answer)`, `record_command(...)`.
6. Next summon within 10 min → step 2 sees those turns → follow-ups resolve. After an
   idle gap > window, continuity resets naturally.

## Error handling

- DB open/IO/corruption/lock failures never propagate to the command path — caught in
  `MemoryService`, degrade to empty context / no-op writes.
- Schema init idempotent.
- Single connection + `threading.Lock` for worker-thread safety.

## Testing (TDD)

sqlite temp file per test; no new external deps (sqlite is stdlib).

- **store**: CRUD round-trips, upsert by key (facts + notes), re-init safe.
- **service**: window boundary (turn at now−9min included, now−11min excluded, mocked
  ts); facts cap honored; fact upsert overwrites; note search; forget by id and by key;
  degraded mode (store raising ⇒ `("", [])`, no exception).
- **tools**: each tool mutates the store correctly; `recall` searches facts + notes.
- **router**: seeded `history` reaches the engine; non-empty `memory_context` lands in
  the system prompt (assert via FakeEngine captured messages); empty defaults preserve
  Phase-1 behavior.

## Out of scope (separate specs)

- Voice: wake word + STT + TTS (Phase 2b).
- Local-model routing via Ollama behind the brain (Phase 2c).
- Automatic fact extraction; habit/routine mining; semantic/vector search; memory
  eviction beyond the injection cap.
