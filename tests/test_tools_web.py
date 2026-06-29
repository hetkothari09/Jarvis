from jarvis.tools.base import Registry
from jarvis.tools import web, build_registry


def test_web_answer_marks_question_for_brain(monkeypatch):
    reg = Registry()
    web.register(reg)
    result = reg.get("web_answer").run(question="weather in Tokyo")
    assert result.ok is True
    assert result.data["question"] == "weather in Tokyo"


def test_build_registry_has_core_tools():
    reg = build_registry()
    names = {s["name"] for s in reg.schemas()}
    assert {"open_app", "close_app", "focus_window", "arrange_window",
            "find_file", "open_path", "set_volume", "media_key",
            "clipboard_get", "clipboard_set", "run_shell", "web_answer"} <= names
