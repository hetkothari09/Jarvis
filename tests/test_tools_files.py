from pathlib import Path
from jarvis.tools.base import Registry
from jarvis.tools import files


def test_find_file_returns_matches(tmp_path, monkeypatch):
    (tmp_path / "resume.pdf").write_text("x")
    (tmp_path / "notes.txt").write_text("y")
    monkeypatch.setattr(files, "_search_roots", lambda: [tmp_path])
    reg = Registry()
    files.register(reg)
    result = reg.get("find_file").run(query="resume")
    assert result.ok is True
    names = [Path(p).name for p in result.data["matches"]]
    assert "resume.pdf" in names and "notes.txt" not in names


def test_find_file_limit(tmp_path, monkeypatch):
    for i in range(30):
        (tmp_path / f"doc{i}.txt").write_text("x")
    monkeypatch.setattr(files, "_search_roots", lambda: [tmp_path])
    reg = Registry()
    files.register(reg)
    result = reg.get("find_file").run(query="doc")
    assert len(result.data["matches"]) <= 20


def test_open_path_calls_startfile(tmp_path, monkeypatch):
    f = tmp_path / "a.txt"
    f.write_text("x")
    opened = []
    monkeypatch.setattr(files, "_open", lambda p: opened.append(p))
    reg = Registry()
    files.register(reg)
    result = reg.get("open_path").run(path=str(f))
    assert result.ok is True and opened == [str(f)]


def test_open_path_missing_returns_error(monkeypatch):
    reg = Registry()
    files.register(reg)
    result = reg.get("open_path").run(path="C:\\does\\not\\exist.xyz")
    assert result.ok is False and "not found" in result.error.lower()
