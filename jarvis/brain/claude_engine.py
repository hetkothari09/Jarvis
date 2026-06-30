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

    def complete(self, messages: list[Msg], tools: list[dict],
                 system: str = "") -> AssistantTurn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=system or SYSTEM_PROMPT,
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
