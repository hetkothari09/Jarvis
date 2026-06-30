from jarvis.brain.engine import Msg, ToolCall
from jarvis.brain.claude_engine import ClaudeEngine


class FakeBlock:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, blocks):
        self.content = blocks


class FakeMessages:
    def __init__(self, response, captured):
        self._response = response
        self._captured = captured
    def create(self, **kwargs):
        self._captured.update(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response, captured):
        self.messages = FakeMessages(response, captured)


def test_parses_tool_use_and_text_blocks():
    captured = {}
    response = FakeResponse([
        FakeBlock("text", text="working on it"),
        FakeBlock("tool_use", id="abc", name="open_app", input={"name": "notepad"}),
    ])
    engine = ClaudeEngine(client=FakeClient(response, captured), model="claude-opus-4-8")
    turn = engine.complete([Msg(role="user", content="open notepad")],
                           [{"name": "open_app", "description": "d", "input_schema": {}}])
    assert turn.text == "working on it"
    assert turn.tool_calls == [ToolCall(id="abc", name="open_app", args={"name": "notepad"})]
    assert captured["model"] == "claude-opus-4-8"
    assert captured["tools"][0]["name"] == "open_app"


def test_translates_tool_result_message():
    captured = {}
    response = FakeResponse([FakeBlock("text", text="done")])
    engine = ClaudeEngine(client=FakeClient(response, captured), model="m")
    messages = [
        Msg(role="user", content="hi"),
        Msg(role="assistant", text=None,
            tool_calls=[ToolCall(id="t1", name="open_app", args={"name": "x"})]),
        Msg(role="tool", tool_call_id="t1", content='{"ok": true}', ok=True),
    ]
    engine.complete(messages, [])
    sent = captured["messages"]
    assert sent[0]["role"] == "user"
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0]["type"] == "tool_use"
    assert sent[2]["role"] == "user"
    assert sent[2]["content"][0]["type"] == "tool_result"
    assert sent[2]["content"][0]["tool_use_id"] == "t1"
