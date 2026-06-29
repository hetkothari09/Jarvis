# JARVIS — Personal Desktop Agent: Design Spec

**Date:** 2026-06-29
**Status:** Approved design, pre-implementation
**Platform:** Windows 11

## Overview

A personalized, always-running "Jarvis"-style desktop assistant. It lives in the
background as a system-tray daemon, is summoned by a global hotkey (and later by
voice), reasons about natural-language commands with an LLM, and carries out real
desktop tasks through a registry of tools (the "hands"). The interface is minimal
and futuristic: a summoned command palette for everyday use, plus an always-on
floating orb that signals presence and listening state.

This document is the agreed design. It is intentionally scoped so the first build
is a thin, working, end-to-end vertical slice, with later capability added in
clearly separated phases.

## Goals

- A single always-on background agent that feels alive but stays out of the way.
- Natural-language commands -> real desktop actions (apps, windows, files, system, web).
- Minimal, futuristic, aesthetic GUI (command palette + floating orb).
- Architecture where new capabilities are added as isolated "tool" plugins without
  touching the core.
- Engine-agnostic brain so a local model can be added later without a rewrite.
- Input-agnostic pipeline so voice plugs into the same path as the hotkey.

## Non-Goals (for now)

- Cross-platform (macOS/Linux) — Windows 11 only initially.
- Multi-user / networked / remote control.
- A heavyweight full-screen HUD as the primary UI (possible optional mode later).
- Fully autonomous background actions without user-initiated commands.

## Decisions (locked)

| Area | Decision | Notes |
|------|----------|-------|
| Tech stack | Python + PySide6 (Qt) | Richest automation/AI ecosystem; Qt for the GUI. |
| Brain | Hybrid (target) | MVP ships **Claude-only**; local (Ollama) router added Phase 2. |
| Input | Hotkey + Voice (target) | MVP ships **hotkey**; voice (wake word + STT + TTS) Phase 2. |
| Capabilities | App/window, file/system, web, workflows | Core set in MVP; workflows Phase 3. |
| GUI | Command Palette (A) + Floating Orb (B) | Palette = everyday driver; orb = always-on presence/voice indicator. |

## Architecture

One background process (system-tray daemon) hosts several isolated modules that
communicate over a central in-process event bus. Each module has one job and a
well-defined interface, so it can be understood, tested, and replaced independently.

```
                    +-----------------------------+
                    |   JARVIS daemon (tray app)   |
                    +--------------+--------------+
                                   |  core event bus
   +----------+----------+---------+--------+--------------+-----------+
   |          |          |         |        |              |           |
[Hotkey]  [Voice]   [GUI:        [Brain]  [Tool          [Memory/    [Config]
 listener  (ph2)     palette+     router   registry]      state]      store
           wake/STT   orb]        L->C
                                   |
                          +--------+--------+
                          | Claude (cloud)  |  <- hard tasks
                          | Ollama (local)  |  <- simple intents (ph2)
                          +-----------------+
                                   |
                    +--------------+---------------+
                    |   Tools (the "hands")         |
                    |  apps . windows . files .     |
                    |  system . web . workflows     |
                    +-------------------------------+
```

**Command flow:** input (hotkey/voice) -> command text event -> Brain router picks
an engine -> engine runs a tool-use loop (calls tools, sees results, repeats until
done) -> result event -> GUI renders it (and speaks it, in Phase 2).

### Key principles

- **Tools are plugins.** Each tool is a self-contained function with a JSON schema
  and a `danger` flag. The Brain only sees schemas. Adding capability means adding a
  tool file; no core changes.
- **Brain is engine-agnostic.** A single engine interface lets the router swap
  Claude <-> Ollama. MVP wires Claude only; local plugs in later with no rewrite.
- **Input is source-agnostic.** Hotkey and voice both emit the same command-text
  event; voice joins the same pipeline later.
- **Dangerous actions are gated.** Destructive or system-power tools require an
  explicit GUI confirmation before running.

## Components

| Module | Job | MVP? | Key libs |
|--------|-----|------|----------|
| `core/daemon` | tray icon, lifecycle, wiring | yes | pystray, PySide6 |
| `core/bus` | event bus (command_in, result_out, state) | yes | in-proc pub/sub |
| `core/config` | settings + secrets (API key, hotkey, theme) | yes | pydantic, keyring |
| `input/hotkey` | global hotkey -> emit command text | yes | pynput / global-hotkeys |
| `input/voice` | wake word + STT + push-to-talk | Phase 2 | RealtimeSTT, openWakeWord |
| `brain/router` | pick engine, run tool-use loop | yes (Claude) | anthropic SDK |
| `brain/engine_local` | Ollama engine, same interface | Phase 2 | ollama |
| `tools/registry` | discover tools, expose schemas | yes | — |
| `tools/*` | apps, windows, files, system, web | yes (core) | pywin32, psutil, pyautogui, pygetwindow |
| `tools/workflows` | named multi-step macros | Phase 3 | — |
| `gui/palette` | summoned command bar + results | yes | PySide6 |
| `gui/orb` | always-on floating orb, state glow | yes | PySide6 frameless |
| `gui/tts` | speak replies | Phase 2 | piper |
| `memory/state` | history, prefs, learned shortcuts | Phase 2 | sqlite |

## MVP Vertical Slice (Phase 1)

The first build proves the whole path works end to end:

1. Daemon launches; tray icon appears and the **orb** sits in a corner (idle glow).
2. Press the **hotkey** (default `Ctrl+Space`) -> the **palette** appears; type a command.
3. Text -> **Brain (Claude)** -> tool-use loop over the **core tools**.
4. Orb pulses while working; palette shows the steps and the final result.
5. A dangerous tool triggers a confirm dialog before running.
6. Esc / click-away hides the palette; the daemon keeps running.

**MVP tool set (the starting "hands"):** `open_app`, `close_app`, `focus_window`,
`arrange_window`, `find_file`, `open_path`, `set_volume`, `media_key`,
`clipboard_get`, `clipboard_set`, `web_answer`, `run_shell` (gated as dangerous).

## Phase Ladder

- **Phase 1 — MVP:** hotkey + Claude + core tools + palette + orb. End-to-end slice.
- **Phase 2:** voice (wake word + STT + TTS), local engine (Ollama) behind the router,
  memory/state (history + preferences).
- **Phase 3:** workflows/macros (named multi-step routines), scheduling, learned
  shortcuts, optional full-HUD summon mode.

## Data Flow (one command)

```
hotkey -> CommandEvent{text, source} -> bus
  -> Router: pick engine (MVP=Claude) -> build messages + tool schemas
  -> tool-use loop:
       engine returns tool_call -> registry runs tool -> ToolResult
       -> feed result back -> repeat until engine returns final text
  -> ResultEvent{text, steps[]} -> bus -> palette renders + orb returns to idle
```

The loop has a **max-steps cap** (default 12) so it cannot run forever. Each tool
call and result is recorded to session history.

### Tool contract

Every tool has the same shape:

```python
@tool(name="open_app", danger=False, schema={ ...JSON schema of args... })
def open_app(name: str) -> ToolResult:   # returns {ok, data | error}
    ...
```

The registry auto-collects decorated tools and feeds their schemas to the Brain.
`danger=True` routes the call through the confirmation gate.

## Error Handling

- A tool failure returns `{ok: false, error}` and never crashes the loop; the Brain
  sees the error and can retry, adapt, or report it.
- Engine/network failure shows a clear error in the palette, flashes the orb red, and
  leaves the daemon running.
- Ambiguous commands let the Brain ask a clarifying question back in the palette
  (e.g. "which Chrome window?").
- A daemon crash relaunches from the tray; config and secrets are persisted.

## Safety

- `danger=True` tools (`run_shell`, file delete/overwrite, system power) show a modal
  confirmation with the exact action before running. No silent destructive operations.
- The API key is stored in the OS keyring, never in plaintext in the repo or config.
- An allowlist for `run_shell` can be added later.

## Testing Strategy

- **Unit:** each tool tested with mocks (no real apps moved); registry schema validation.
- **Brain:** router tested with a fake engine returning scripted tool_calls; assert it
  calls the right tools, respects the max-steps cap, and handles tool errors.
- **Integration:** drive `command -> result` through the bus with stub tools.
- **Manual smoke:** a real-desktop checklist per phase (open app, snap window, find file).
- **GUI:** light — manual plus a few widget-state tests (orb reflects current state).

## Open Items / Future

- Wake-word phrase and TTS voice selection (Phase 2).
- Hybrid router policy: which intents go local vs cloud (Phase 2).
- Color theme tokens for the futuristic look (settled during GUI build).
- Optional full-HUD summon mode (Phase 3).
