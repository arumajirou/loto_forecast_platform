from __future__ import annotations

import argparse
import ast
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from loto.orchestration import formal_backtest_entrypoint_support as support
from loto.orchestration.formal_backtest_execution import run_instrumented_fold

MAIN_SOURCE = Path(__file__).resolve().parents[2] / "src/loto/orchestration/formal_backtest_main.py"


def fake_parser_module() -> ModuleType:
    module = ModuleType("fake_formal_backtest")

    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument("--resume", action="store_true", default=True)
        parser.add_argument("--fail-fast", action="store_true", default=True)
        return parser

    module.build_parser = build_parser
    return module


def test_parser_defaults_to_non_resume_lane() -> None:
    parser = support.build_parser(fake_parser_module())
    args = parser.parse_args([])
    assert args.resume is False
    assert args.fail_fast is True
    assert parser.parse_args(["--resume"]).resume is True
    assert parser.parse_args(["--no-fail-fast"]).fail_fast is False


def test_git_blob_sha_matches_git_object_rule(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("print('ok')\n", encoding="utf-8")
    import hashlib

    payload = path.read_bytes()
    expected = hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload,
        usedforsecurity=False,
    ).hexdigest()
    assert support.git_blob_sha(path) == expected


def test_source_pin_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "legacy.py"
    path.write_text("def build_parser():\n    return None\n", encoding="utf-8")
    with pytest.raises(support.FormalBacktestEntrypointError, match="source changed"):
        support.load_legacy_module(path)


def test_runtime_events_precede_leakage_check() -> None:
    order: list[str] = []

    class Recorder:
        def record_prediction_ready(self, **_: object) -> None:
            order.append("predict")

        def record_actual_read(self, **_: object) -> None:
            order.append("actual")

    module = SimpleNamespace(
        resolve_model_params=lambda spec, stage: {"stage": stage},
        torch=SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: False,
                reset_peak_memory_stats=lambda: None,
            )
        ),
        collect_gpu_evidence=lambda gpu_required: {
            "vram_allocated_bytes": 0,
            "vram_peak_bytes": 0,
            "cuda_available": False,
        },
        run_model_fold_internal=lambda *args: (
            np.full(37, 7 / 37, dtype=float),
            np.arange(1, 8, dtype=float),
            "cpu",
            None,
        ),
        np=np,
        execute_leakage_checks=lambda *args: order.append("leakage") or {"status": "PASS"},
    )
    result = run_instrumented_fold(
        module=module,
        recorder=Recorder(),
        model_id="baseline",
        fold_id="fold-4",
        spec=SimpleNamespace(),
        train_df=object(),
        test_row=object(),
        full_df=object(),
        test_idx=3,
        seed=1,
        device="cpu",
        precision="32",
        stage="smoke",
    )
    assert order == ["predict", "actual", "leakage"]
    assert result[5] == {"status": "PASS"}


def test_target_materialization_occurs_after_instrumented_fold() -> None:
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    fold_call = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_instrumented_fold"
    )
    target_read = next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "actual_pos"
            for target in node.targets
        )
    )
    assert fold_call < target_read
