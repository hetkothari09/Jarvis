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
