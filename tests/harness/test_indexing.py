from pathlib import Path

from loto.harness.indexing.python_ast import parse_python_file
from loto.harness.indexing.sqlite_index import SQLiteCodeIndex


def test_python_symbol_index_tracks_lines_calls_and_sha(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "pkg" / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        '''class Worker:
    """Runs one task."""

    def run(self, value: int) -> int:
        return helper(value)


def helper(value: int) -> int:
    return value + 1
''',
        encoding="utf-8",
    )
    symbols = parse_python_file(source, repo)
    names = {symbol.qualified_name for symbol in symbols}
    assert names == {"Worker", "Worker.run", "helper"}
    run_symbol = next(symbol for symbol in symbols if symbol.qualified_name == "Worker.run")
    assert "helper" in run_symbol.calls
    assert run_symbol.start_line < run_symbol.end_line
    assert len(run_symbol.content_sha256) == 64

    index = SQLiteCodeIndex(tmp_path / "index.sqlite3")
    try:
        first = index.index_repository(repo)
        assert first["indexed_files"] == 1
        assert first["indexed_symbols"] == 3
        second = index.index_repository(repo)
        assert second["skipped_files"] == 1
        hits = index.search("Worker.run")
        assert hits[0]["qualified_name"] == "Worker.run"
    finally:
        index.close()
