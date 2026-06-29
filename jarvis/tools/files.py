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
