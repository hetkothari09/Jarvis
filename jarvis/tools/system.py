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
