import pytest
from jarvis.tools.base import ToolResult, tool, Registry


def test_toolresult_helpers():
    ok = ToolResult.ok({"x": 1})
    err = ToolResult.err("nope")
    assert ok.ok is True and ok.data == {"x": 1} and ok.error is None
    assert err.ok is False and err.error == "nope" and err.data is None


def test_registry_collects_and_runs():
    reg = Registry()

    @tool(reg, name="add", description="add two ints",
          schema={"type": "object",
                  "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                  "required": ["a", "b"]})
    def add(a: int, b: int) -> ToolResult:
        return ToolResult.ok(a + b)

    assert reg.get("add").run(a=2, b=3).data == 5
    schemas = reg.schemas()
    assert schemas[0]["name"] == "add"
    assert schemas[0]["input_schema"]["required"] == ["a", "b"]


def test_danger_flag_defaults_false_and_can_be_set():
    reg = Registry()

    @tool(reg, name="safe", description="", schema={"type": "object", "properties": {}})
    def safe() -> ToolResult:
        return ToolResult.ok(None)

    @tool(reg, name="risky", description="", schema={"type": "object", "properties": {}},
          danger=True)
    def risky() -> ToolResult:
        return ToolResult.ok(None)

    assert reg.get("safe").danger is False
    assert reg.get("risky").danger is True


def test_unknown_tool_raises():
    reg = Registry()
    with pytest.raises(KeyError):
        reg.get("missing")


def test_run_wraps_exceptions_as_error_result():
    reg = Registry()

    @tool(reg, name="boom", description="", schema={"type": "object", "properties": {}})
    def boom() -> ToolResult:
        raise RuntimeError("kaboom")

    result = reg.get("boom").run()
    assert result.ok is False and "kaboom" in result.error
