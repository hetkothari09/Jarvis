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
