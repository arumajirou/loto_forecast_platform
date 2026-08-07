from __future__ import annotations

from pathlib import Path

import pytest

from loto.adapters.gluonts.p6_models import build_matrix, matrix_sha256
from loto.gluonts_campaign.p6_matrix import (
    LaneMatrixInvocation,
    aggregate_matrices,
)


def invocation(lane: str, tmp_path: Path, importer) -> LaneMatrixInvocation:
    matrix = build_matrix(lane, construct=False, importer=importer)
    run_dir = tmp_path / lane
    run_dir.mkdir()
    matrix_path = run_dir / "P6_CONSTRUCTOR_MATRIX.json"
    matrix_path.write_text(matrix.model_dump_json(), encoding="utf-8")
    return LaneMatrixInvocation(
        lane=lane,
        matrix=matrix,
        run_dir=run_dir,
        matrix_path=matrix_path,
        stdout_path=run_dir / "stdout.log",
        stderr_path=run_dir / "stderr.log",
        return_code=0,
        matrix_sha256=matrix_sha256(matrix),
    )


def flexible_importer(module_name: str):
    import types

    from loto.adapters.gluonts.p6_models import PROFILES

    class Estimator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module = types.ModuleType(module_name)
    profile = next(profile for profile in PROFILES if profile.module == module_name)
    setattr(module, profile.name, Estimator)
    return module


def test_cross_lane_matrix_preserves_all_models(tmp_path: Path) -> None:
    compat = invocation("compat", tmp_path, flexible_importer)
    latest = invocation("latest", tmp_path, flexible_importer)
    output = tmp_path / "P6_CROSS_LANE_MATRIX.json"
    matrix = aggregate_matrices(compat, latest, output)
    assert matrix.all_models_present is True
    assert len(matrix.entries) == 9
    assert all(entry.planned_kwargs_equal for entry in matrix.entries)
    assert output.exists()


def test_cross_lane_matrix_rejects_reversed_lanes(tmp_path: Path) -> None:
    compat = invocation("compat", tmp_path, flexible_importer)
    latest = invocation("latest", tmp_path, flexible_importer)
    with pytest.raises(ValueError, match="compat and latest"):
        aggregate_matrices(latest, compat)
