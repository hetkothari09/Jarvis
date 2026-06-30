"""Provider-neutral conversation types and the Engine interface.

The router speaks only these types. Each concrete engine (Claude, later Ollama)
translates them to/from its provider format. FakeEngine is used in tests.
"""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Msg:
    role: str                       # "user" | "assistant" | "tool"
    content: str | None = None      # text for user/tool messages
    text: str | None = None         # assistant free text
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None # for role == "tool"
    ok: bool = True                 # for role == "tool"


@dataclass
class AssistantTurn:
    text: str | None
    tool_calls: list[ToolCall]

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class Engine(Protocol):
    def complete(self, messages: list[Msg], tools: list[dict]) -> AssistantTurn:
        ...


class FakeEngine:
    """Returns pre-scripted turns; ignores inputs. For tests only."""
    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)

    def complete(self, messages: list[Msg], tools: list[dict]) -> AssistantTurn:
        return self._turns.pop(0)
