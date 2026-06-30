"""High-level memory API. Hides sqlite, windowing, and fact rendering, and
degrades gracefully so a storage failure never breaks a command."""
import logging

from jarvis.brain.engine import Msg

log = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, store, *, window_min: int = 10, max_facts: int = 100) -> None:
        self._store = store
        self._window_s = window_min * 60
        self._max_facts = max_facts

    def session_context(self, now: float) -> tuple:
        try:
            facts = self._store.list_facts()[: self._max_facts]
            block = "\n".join(self._render_fact(k, t) for _, k, t in facts)
            rows = self._store.turns_since(now - self._window_s)
            turns = [self._turn_msg(role, text) for role, text in rows]
            return block, turns
        except Exception:
            log.exception("memory session_context failed")
            return "", []

    @staticmethod
    def _render_fact(key, text) -> str:
        return f"- {key}: {text}" if key else f"- {text}"

    @staticmethod
    def _turn_msg(role: str, text: str) -> Msg:
        if role == "assistant":
            return Msg(role="assistant", text=text)
        return Msg(role="user", content=text)

    def record_turn(self, role: str, text: str, ts: float) -> None:
        self._safe(lambda: self._store.add_turn(role, text, ts))

    def record_command(self, text: str, ok: bool, summary: str, ts: float) -> None:
        self._safe(lambda: self._store.add_command(text, ok, summary, ts))

    def add_fact(self, text: str, key=None, *, now: float) -> None:
        self._safe(lambda: self._store.add_fact(text, key, now=now))

    def list_facts(self) -> list:
        return self._safe(lambda: self._store.list_facts(), default=[])

    def forget_fact(self, id_or_key) -> bool:
        return bool(self._safe(
            lambda: self._store.delete_fact(**self._fact_selector(id_or_key)),
            default=False))

    def add_note(self, key: str, text: str, *, now: float) -> None:
        self._safe(lambda: self._store.upsert_note(key, text, now=now))

    def get_note(self, key: str):
        return self._safe(lambda: self._store.get_note(key), default=None)

    def search_notes(self, query: str) -> list:
        return self._safe(lambda: self._store.search_notes(query), default=[])

    def forget_note(self, key: str) -> bool:
        return bool(self._safe(lambda: self._store.delete_note(key), default=False))

    @staticmethod
    def _fact_selector(id_or_key) -> dict:
        s = str(id_or_key)
        return {"id": int(s)} if s.isdigit() else {"key": s}

    @staticmethod
    def _safe(fn, default=None):
        try:
            return fn()
        except Exception:
            log.exception("memory operation failed")
            return default
