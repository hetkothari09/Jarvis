"""Lightweight web/answer marker tool.

Phase 1 keeps this minimal: it echoes the question back so the Brain answers
from its own knowledge. Phase 2 replaces the body with a real fetch/search.
"""
from jarvis.tools.base import Registry, ToolResult, tool


def register(reg: Registry) -> None:
    @tool(reg, name="web_answer",
          description="Answer a general-knowledge or web-style question.",
          schema={"type": "object",
                  "properties": {"question": {"type": "string"}},
                  "required": ["question"]})
    def web_answer(question: str) -> ToolResult:
        return ToolResult.ok({"question": question})
