from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loto.adapters.gluonts.p6_models import (
    EXPECTED_ESTIMATORS,
    P6ConstructorMatrix,
    canonical_json_bytes,
    matrix_sha256,
)


@dataclass(frozen=True)
class LaneMatrixInvocation:
    lane: Literal["compat", "latest"]
    matrix: P6ConstructorMatrix
    run_dir: Path
    matrix_path: Path
    stdout_path: Path
    stderr_path: Path
    return_code: int
    matrix_sha256: str


class CrossLaneEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_name: str
    compat_formal_state: str
    latest_formal_state: str
    signature_equal: bool
    planned_kwargs_equal: bool


class P6CrossLaneMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    compat_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    latest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: list[CrossLaneEntry]
    all_models_present: bool

    @model_validator(mode="after")
    def validate_entries(self) -> P6CrossLaneMatrix:
        if [entry.model_name for entry in self.entries] != list(EXPECTED_ESTIMATORS):
            raise ValueError("cross-lane matrix must preserve canonical estimator order")
        return self


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


def invoke_lane_matrix(
    lane: Literal["compat", "latest"],
    command: Sequence[str],
    artifact_root: Path,
    *,
    construct: bool = False,
    timeout_seconds: float = 300.0,
) -> LaneMatrixInvocation:
    if not command:
        raise ValueError("lane command cannot be empty")
    run_dir = artifact_root / lane
    run_dir.mkdir(parents=True, exist_ok=False)
    matrix_path = run_dir / "P6_CONSTRUCTOR_MATRIX.json"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    arguments = [*command, "--output", str(matrix_path)]
    if construct:
        arguments.append("--construct")
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if not matrix_path.exists():
        raise RuntimeError(f"{lane} provider did not produce P6_CONSTRUCTOR_MATRIX.json")
    matrix = P6ConstructorMatrix.model_validate_json(matrix_path.read_text("utf-8"))
    if matrix.lane != lane or matrix.construct_requested is not construct:
        raise ValueError(f"{lane} matrix identity mismatch")
    calculated_sha = matrix_sha256(matrix)
    persisted_sha = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    if persisted_sha != calculated_sha:
        raise ValueError(f"{lane} matrix SHA-256 mismatch")
    return LaneMatrixInvocation(
        lane=lane,
        matrix=matrix,
        run_dir=run_dir,
        matrix_path=matrix_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        return_code=completed.returncode,
        matrix_sha256=calculated_sha,
    )


def aggregate_matrices(
    compat: LaneMatrixInvocation,
    latest: LaneMatrixInvocation,
    output_path: Path | None = None,
) -> P6CrossLaneMatrix:
    if compat.lane != "compat" or latest.lane != "latest":
        raise ValueError("aggregate_matrices requires compat and latest invocations")
    compat_entries = {entry.model_name: entry for entry in compat.matrix.entries}
    latest_entries = {entry.model_name: entry for entry in latest.matrix.entries}
    names_match = (
        tuple(compat_entries) == EXPECTED_ESTIMATORS
        and tuple(latest_entries) == EXPECTED_ESTIMATORS
    )
    entries = []
    for name in EXPECTED_ESTIMATORS:
        left = compat_entries[name]
        right = latest_entries[name]
        entries.append(
            CrossLaneEntry(
                model_name=name,
                compat_formal_state=left.formal_state.value,
                latest_formal_state=right.formal_state.value,
                signature_equal=left.constructor_signature == right.constructor_signature,
                planned_kwargs_equal=left.planned_kwargs == right.planned_kwargs,
            )
        )
    matrix = P6CrossLaneMatrix(
        compat_sha256=compat.matrix_sha256,
        latest_sha256=latest.matrix_sha256,
        entries=entries,
        all_models_present=names_match,
    )
    if output_path is not None:
        atomic_write(output_path, matrix.model_dump(mode="json"))
    return matrix
