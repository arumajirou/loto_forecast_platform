from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..security import sha256_text


class PythonSymbol(BaseModel):
    path: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    docstring: str | None = None
    calls: list[str] = Field(default_factory=list)
    content_sha256: str


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, source: str, path: str) -> None:
        self.source = source
        self.path = path
        self.stack: list[str] = []
        self.symbols: list[PythonSymbol] = []

    def _calls(self, node: ast.AST) -> list[str]:
        result: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            target = child.func
            if isinstance(target, ast.Name):
                result.add(target.id)
            elif isinstance(target, ast.Attribute):
                parts: list[str] = []
                current: ast.AST = target
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                result.add(".".join(reversed(parts)))
        return sorted(result)

    @staticmethod
    def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(base) for base in node.bases)
            return f"class {node.name}({bases})" if bases else f"class {node.name}"
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}{ast.unparse(node.args)}"

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        qualified = ".".join([*self.stack, node.name])
        segment = ast.get_source_segment(self.source, node) or ""
        self.symbols.append(
            PythonSymbol(
                path=self.path,
                qualified_name=qualified,
                kind=(
                    "class"
                    if isinstance(node, ast.ClassDef)
                    else "async_function"
                    if isinstance(node, ast.AsyncFunctionDef)
                    else "function"
                ),
                start_line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                signature=self._signature(node),
                docstring=ast.get_docstring(node, clean=True),
                calls=self._calls(node),
                content_sha256=sha256_text(segment),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._record(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._record(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._record(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def parse_python_file(path: str | Path, root: str | Path | None = None) -> list[PythonSymbol]:
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path), type_comments=True)
    relative = source_path.relative_to(Path(root)) if root else source_path
    visitor = _SymbolVisitor(source, relative.as_posix())
    visitor.visit(tree)
    return visitor.symbols
