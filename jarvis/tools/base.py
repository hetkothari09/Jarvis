"""Tool contract: a uniform result type, a registration decorator, and a registry."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    @staticmethod
    def ok_(data: Any = None) -> "ToolResult":  # internal alias to avoid name clash
        return ToolResult(ok=True, data=data)

    @classmethod
    def err(cls, message: str) -> "ToolResult":
        return cls(ok=False, error=message)


# Public constructor for success (kept readable at call sites).
def _ok(data: Any = None) -> ToolResult:
    return ToolResult(ok=True, data=data)


ToolResult.ok = staticmethod(_ok)  # ToolResult.ok({...}) -> success result


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    danger: bool
    func: Callable[..., ToolResult]

    def run(self, **kwargs: Any) -> ToolResult:
        try:
            return self.func(**kwargs)
        except Exception as exc:  # tools never crash the loop
            return ToolResult.err(f"{type(exc).__name__}: {exc}")


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, t: Tool) -> None:
        self._tools[t.name] = t

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def schemas(self) -> list[dict]:
        # Anthropic tool format: name, description, input_schema.
        return [
            {"name": t.name, "description": t.description, "input_schema": t.schema}
            for t in self._tools.values()
        ]


def tool(registry: "Registry", *, name: str, description: str, schema: dict,
         danger: bool = False) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    def decorate(func: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        registry.add(Tool(name=name, description=description, schema=schema,
                          danger=danger, func=func))
        return func

    return decorate
