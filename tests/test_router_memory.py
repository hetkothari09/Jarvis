from jarvis.brain.engine import AssistantTurn, Msg, FakeEngine
from jarvis.brain.router import run_command, SYSTEM_PROMPT
from jarvis.tools.base import Registry


def _noop_step(call, res):
    pass


def test_history_and_memory_context_reach_engine():
    eng = FakeEngine([AssistantTurn(text="done", tool_calls=[])])
    history = [Msg(role="user", content="open notepad"),
               Msg(role="assistant", text="opened notepad")]
    out = run_command("do it again", Registry(), eng,
                      confirm=lambda c: True, on_step=_noop_step,
                      history=history, memory_context="- name: Het")
    assert out == "done"
    assert eng.last_messages[0].content == "open notepad"
    assert eng.last_messages[-1].content == "do it again"
    assert "Known about the user:" in eng.last_system
    assert "- name: Het" in eng.last_system
    assert SYSTEM_PROMPT in eng.last_system


def test_defaults_preserve_phase1_behavior():
    eng = FakeEngine([AssistantTurn(text="ok", tool_calls=[])])
    out = run_command("hi", Registry(), eng,
                      confirm=lambda c: True, on_step=_noop_step)
    assert out == "ok"
    assert len(eng.last_messages) == 1
    assert eng.last_system == SYSTEM_PROMPT
    assert "Known about the user" not in eng.last_system
