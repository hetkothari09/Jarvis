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
