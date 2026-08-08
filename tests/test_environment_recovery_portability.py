from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "experiments" / "capture_main_environment_recovery.py"


def _literal_string_lists(tree: ast.AST) -> list[list[str]]:
    lists: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        values: list[str] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                break
            values.append(element.value)
        else:
            lists.append(values)
    return lists


def test_package_inventory_uses_uv_environment_discovery() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert ["uv", "pip", "list"] in _literal_string_lists(tree)
    assert ".venv/bin/python" not in source
    assert ".venv\\Scripts\\python.exe" not in source
