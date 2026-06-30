"""Model-facing memory tools. Registered only when a MemoryService exists."""
import time

from jarvis.memory.service import MemoryService
from jarvis.tools.base import Registry, ToolResult, tool


def register(reg: Registry, mem: MemoryService) -> None:
    @tool(reg, name="remember_fact",
          description="Store a durable fact or preference about the user. Pass a "
                      "stable 'key' (e.g. 'editor') to overwrite a prior value.",
          schema={"type": "object",
                  "properties": {"text": {"type": "string"},
                                 "key": {"type": "string"}},
                  "required": ["text"]})
    def remember_fact(text, key=None):
        mem.add_fact(text, key, now=time.time())
        return ToolResult.ok({"remembered": text, "key": key})

    @tool(reg, name="recall",
          description="Search stored facts and notes for anything matching the query.",
          schema={"type": "object",
                  "properties": {"query": {"type": "string"}},
                  "required": ["query"]})
    def recall(query):
        q = query.lower()
        facts = [t for _, k, t in mem.list_facts()
                 if q in (t or "").lower() or q in (k or "").lower()]
        notes = mem.search_notes(query)
        return ToolResult.ok({"facts": facts, "notes": notes})

    @tool(reg, name="save_note",
          description="Save a named note. Reusing a key overwrites the note.",
          schema={"type": "object",
                  "properties": {"key": {"type": "string"},
                                 "text": {"type": "string"}},
                  "required": ["key", "text"]})
    def save_note(key, text):
        mem.add_note(key, text, now=time.time())
        return ToolResult.ok({"saved": key})

    @tool(reg, name="forget",
          description="Delete a stored fact (by key or numeric id) or a note (by key).",
          schema={"type": "object",
                  "properties": {"key_or_id": {"type": "string"}},
                  "required": ["key_or_id"]})
    def forget(key_or_id):
        removed = mem.forget_fact(key_or_id) or mem.forget_note(str(key_or_id))
        return ToolResult.ok({"forgotten": key_or_id, "removed": removed})
