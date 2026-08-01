from __future__ import annotations

import argparse
import ast
from pathlib import Path


def _is_self_feature_columns(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr == "feature_columns"
    )


def _is_numeric_feature_columns_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "numeric_feature_columns"
    )


def _find_assignment(tree: ast.AST) -> ast.Assign | ast.AnnAssign | None:
    for class_node in ast.walk(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue
        if class_node.name != "RuntimeModel":
            continue

        for function_node in class_node.body:
            if not isinstance(
                function_node,
                ast.FunctionDef | ast.AsyncFunctionDef,
            ):
                continue
            if function_node.name != "fit_candidate":
                continue

            for node in ast.walk(function_node):
                if isinstance(node, ast.Assign):
                    if (
                        len(node.targets) == 1
                        and _is_self_feature_columns(node.targets[0])
                        and _is_numeric_feature_columns_call(node.value)
                    ):
                        return node
                elif isinstance(node, ast.AnnAssign):
                    if (
                        _is_self_feature_columns(node.target)
                        and node.value is not None
                        and _is_numeric_feature_columns_call(node.value)
                    ):
                        return node
    return None


def _already_safe(text: str) -> bool:
    return "if column != target_column" in text and "target column leaked into features" in text


def patch_factory_text(text: str) -> tuple[str, bool]:
    if _already_safe(text):
        return text, False

    tree = ast.parse(text)
    assignment = _find_assignment(tree)
    if assignment is None:
        raise RuntimeError(
            "Could not find RuntimeModel.fit_candidate() assignment "
            "`self.feature_columns = numeric_feature_columns(...)`."
        )

    if not hasattr(assignment, "end_lineno"):
        raise RuntimeError("Python AST does not expose source positions.")

    lines = text.splitlines(keepends=True)
    start = assignment.lineno - 1
    end = assignment.end_lineno
    source_line = lines[start]
    indent = source_line[: len(source_line) - len(source_line.lstrip())]

    replacement = [
        f"{indent}self.feature_columns = [\n",
        f"{indent}    column\n",
        f"{indent}    for column in numeric_feature_columns(train)\n",
        f"{indent}    if column != target_column\n",
        f"{indent}]\n",
        f"{indent}if target_column in self.feature_columns:\n",
        f"{indent}    raise RuntimeError(\n",
        f'{indent}        f"target column leaked into features: {{target_column}}"\n',
        f"{indent}    )\n",
    ]

    patched = "".join(lines[:start] + replacement + lines[end:])
    ast.parse(patched)
    return patched, True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default="src/loto/models/factory.py",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    text = path.read_text(encoding="utf-8")
    patched, changed = patch_factory_text(text)

    if args.check:
        if changed:
            raise SystemExit("FACTORY_PATCH_REQUIRED: target_column is not excluded")
        print("PASS: factory target exclusion already present")
        return

    if changed:
        path.write_text(patched, encoding="utf-8")
        print(f"PATCHED={path.resolve()}")
    else:
        print(f"UNCHANGED={path.resolve()}")


if __name__ == "__main__":
    main()
