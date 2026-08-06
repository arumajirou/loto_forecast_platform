from __future__ import annotations

import ast
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from loto.data_access_ledger.contracts import AccessMode, DataAccessLedger


class StaticAccessFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    path: str
    line: int = Field(ge=1)
    call: str
    expected_mode: AccessMode
    message: str


_READ_CALLS = {
    "builtins.open",
    "open",
    "pandas.read_csv",
    "pandas.read_excel",
    "pandas.read_feather",
    "pandas.read_json",
    "pandas.read_parquet",
    "pandas.read_pickle",
    "pandas.read_sql",
    "pandas.read_sql_query",
    "pandas.read_sql_table",
    "polars.read_csv",
    "polars.read_database",
    "polars.read_excel",
    "polars.read_json",
    "polars.read_parquet",
    "pyarrow.parquet.read_table",
}
_PATH_READ_METHODS = {"open", "read_bytes", "read_text"}
_JOIN_METHODS = {"concat", "join", "merge"}
_FIT_METHODS = {"fit", "partial_fit"}


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value, aliases)
        if parent is None:
            return node.attr
        return f"{parent}.{node.attr}"
    return None


def _classify_call(name: str) -> AccessMode | None:
    leaf = name.rsplit(".", 1)[-1]
    if name in _READ_CALLS or leaf in _PATH_READ_METHODS:
        return AccessMode.READ
    if leaf in _FIT_METHODS:
        return AccessMode.FIT
    if leaf == "fit_transform":
        return AccessMode.TRANSFORM_FIT
    if leaf in _JOIN_METHODS:
        return AccessMode.JOIN
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {"open": "builtins.open"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = f"{node.module}.{item.name}"
    return aliases


def scan_python_source(
    source: str,
    *,
    path: str,
    ledger: DataAccessLedger,
) -> list[StaticAccessFinding]:
    """Find data-access calls without a matching ledger event at the same source line."""

    normalized_path = str(PurePosixPath(path.replace("\\", "/")))
    tree = ast.parse(source, filename=normalized_path)
    aliases = _import_aliases(tree)
    declarations: dict[tuple[str, int], set[AccessMode]] = {}
    for event in ledger.events:
        key = (event.location.path, event.location.line)
        declarations.setdefault(key, set()).add(event.mode)

    findings: list[StaticAccessFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_name(node.func, aliases)
        if name is None:
            continue
        expected_mode = _classify_call(name)
        if expected_mode is None:
            continue
        declared_modes = declarations.get((normalized_path, node.lineno), set())
        if expected_mode in declared_modes:
            continue
        code = "UNDECLARED_DATA_ACCESS" if not declared_modes else "ACCESS_MODE_MISMATCH"
        findings.append(
            StaticAccessFinding(
                code=code,
                path=normalized_path,
                line=node.lineno,
                call=name,
                expected_mode=expected_mode,
                message=(
                    f"{name} requires a {expected_mode.value} ledger event at "
                    f"{normalized_path}:{node.lineno}"
                ),
            )
        )

    findings.sort(key=lambda item: (item.path, item.line, item.call))
    return findings
