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
