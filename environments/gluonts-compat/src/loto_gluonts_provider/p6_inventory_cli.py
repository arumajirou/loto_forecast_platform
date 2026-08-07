from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from . import LANE
from .p6_models import FormalState, P6ConstructorMatrix, build_matrix, canonical_json_bytes


def runtime_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in ("gluonts", "torch", "lightning", "pytorch-lightning", "pydantic"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def atomic_write(path: Path, payload: Any) -> str:
    content = canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GluonTS P6 nine-estimator constructor matrix")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--construct", action="store_true")
    return parser


def exit_code(matrix: P6ConstructorMatrix) -> int:
    if matrix.summary[FormalState.FAILED.value] > 0:
        return 1
    target = (
        FormalState.CONSTRUCTED_ONLY
        if matrix.construct_requested
        else FormalState.DISCOVERED_ONLY
    )
    if matrix.summary[target.value] != 9:
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    matrix = build_matrix(
        LANE,
        construct=args.construct,
        runtime_versions=runtime_versions(),
    )
    sha256 = atomic_write(args.output, matrix.model_dump(mode="json"))
    print(
        json.dumps(
            {
                "lane": LANE,
                "construct_requested": args.construct,
                "output": str(args.output),
                "sha256": sha256,
                "summary": matrix.summary,
            },
            sort_keys=True,
        )
    )
    return exit_code(matrix)


if __name__ == "__main__":
    raise SystemExit(main())
