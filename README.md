# JARVIS — Personal Desktop Agent (Phase 1 MVP)

Always-on Windows tray agent. Press `Ctrl+Space`, type a command, and JARVIS uses
Claude + desktop tools to do it. A floating orb shows its state; dangerous actions
ask before running.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -c "from jarvis.core.config import set_api_key; set_api_key('sk-ant-...')"
```

## Run

```powershell
python -m jarvis
```

Tray icon + orb appear. Press `Ctrl+Space` to summon the command palette.

## Test

```powershell
pytest
```

(38 tests; all desktop side-effects are mocked, so nothing on your machine moves.)

## What it can do (Phase 1)

Open/close apps, focus/arrange windows, find/open files, set volume, media keys,
clipboard read/write, a gated shell, and general answers. Dangerous actions
(`run_shell`, `close_app`) require a confirmation click first.

## Architecture

- `jarvis/core` — daemon, event bus, config + keyring secrets
- `jarvis/brain` — provider-agnostic tool-use loop (`router`), neutral types
  (`engine`), Claude implementation (`claude_engine`)
- `jarvis/tools` — desktop tools as registered plugins (apps, windows, files,
  system, web)
- `jarvis/gui` — floating orb, command palette, theme
- `jarvis/input` — global hotkey listener

See `docs/superpowers/specs/` and `docs/superpowers/plans/` for the design and plan.

## Next phases

- **Phase 2:** voice (wake word + STT + TTS), local model (Ollama) behind the
  router, memory/state.
- **Phase 3:** workflows/macros, scheduling, optional full-HUD summon mode.
