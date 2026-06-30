from jarvis.brain.engine import Msg, ToolCall, AssistantTurn, FakeEngine


def test_assistant_turn_final_vs_tools():
    final = AssistantTurn(text="done", tool_calls=[])
    acting = AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="open_app",
                                                           args={"name": "notepad"})])
    assert final.is_final is True
    assert acting.is_final is False


def test_fake_engine_returns_scripted_turns_in_order():
    turns = [
        AssistantTurn(text=None, tool_calls=[ToolCall(id="1", name="x", args={})]),
        AssistantTurn(text="all done", tool_calls=[]),
    ]
    engine = FakeEngine(turns)
    assert engine.complete([Msg(role="user", content="hi")], []).tool_calls[0].name == "x"
    assert engine.complete([], []).text == "all done"
