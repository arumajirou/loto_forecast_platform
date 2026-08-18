from __future__ import annotations

import pathlib

from scripts.check_ruff_format_baseline import (
    classify,
    extract_unformatted,
    read_baseline,
)


def test_extract_unformatted_paths() -> None:
    output = """
unformatted: File would be reformatted
   --> src/example.py:10:5
unformatted: File would be reformatted
   --> tests/test_example.py:20:1
"""

    assert extract_unformatted(output) == {
        "src/example.py",
        "tests/test_example.py",
    }


def test_classify_allows_only_inherited_debt() -> None:
    inherited, resolved, introduced = classify(
        baseline={"old.py", "fixed.py"},
        current={"old.py"},
    )

    assert inherited == {"old.py"}
    assert resolved == {"fixed.py"}
    assert introduced == set()


def test_classify_rejects_new_debt() -> None:
    inherited, resolved, introduced = classify(
        baseline={"old.py"},
        current={"old.py", "new.py"},
    )

    assert inherited == {"old.py"}
    assert resolved == set()
    assert introduced == {"new.py"}


def test_read_baseline_ignores_comments(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "baseline.txt"
    path.write_text(
        "# comment\n"
        "\n"
        "src/a.py\n"
        "tests/b.py\n",
        encoding="utf-8",
    )

    assert read_baseline(path) == {
        "src/a.py",
        "tests/b.py",
    }
