from __future__ import annotations

import ast
from pathlib import Path


def test_pure_core_does_not_import_subprocess() -> None:
    root = Path(__file__).resolve().parents[2] / "src/loto/provider_sandbox"
    for name in ("contracts.py", "validation.py", "argv.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert "subprocess" not in imports


def test_executor_uses_shell_false() -> None:
    root = Path(__file__).resolve().parents[2] / "src/loto/provider_sandbox/executor.py"
    source = root.read_text(encoding="utf-8")
    assert "shell=False" in source
    assert "shell=True" not in source
