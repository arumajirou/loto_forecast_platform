from __future__ import annotations

from pathlib import Path


def test_core_evaluator_does_not_import_subprocess() -> None:
    root = Path(__file__).parents[2]
    for name in ("contracts.py", "evaluator.py"):
        source = (root / "src" / "loto" / "clock_health" / name).read_text(
            encoding="utf-8"
        )
        assert "import subprocess" not in source
        assert "subprocess.run" not in source


def test_adapter_uses_shell_false_and_fixed_argv() -> None:
    root = Path(__file__).parents[2]
    source = (root / "src" / "loto" / "clock_health" / "chronyc.py").read_text(
        encoding="utf-8"
    )
    assert 'shell=False' in source
    assert '("chronyc", "-n", "tracking")' in source
    assert '("chronyc", "-n", "sources", "-v")' in source
