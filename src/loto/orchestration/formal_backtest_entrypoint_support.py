from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from loto.orchestration.formal_backtest_ledger import FormalBacktestDatasetEvidence

ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCRIPT = ROOT / "scripts" / "run_formal_model_backtest.py"
EXPECTED_LEGACY_GIT_BLOB_SHA = "fcf3aa745f209aedf1809a3fa2e32da66b4c2859"


class FormalBacktestEntrypointError(RuntimeError):
    """Raised when the pinned instrumented entrypoint cannot run safely."""


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise FormalBacktestEntrypointError(f"artifact is a symlink: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def load_legacy_module(path: Path = LEGACY_SCRIPT) -> ModuleType:
    if not path.is_file() or path.is_symlink():
        raise FormalBacktestEntrypointError(
            f"legacy formal-backtest script must be a regular file: {path}"
        )
    observed = git_blob_sha(path)
    if observed != EXPECTED_LEGACY_GIT_BLOB_SHA:
        raise FormalBacktestEntrypointError(
            "legacy formal-backtest source changed; expected Git blob "
            f"{EXPECTED_LEGACY_GIT_BLOB_SHA}, observed {observed}"
        )
    spec = importlib.util.spec_from_file_location("_loto_formal_backtest_pinned", path)
    if spec is None or spec.loader is None:
        raise FormalBacktestEntrypointError(f"cannot load legacy script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_parser(module: ModuleType) -> argparse.ArgumentParser:
    parser = module.build_parser()
    parser.set_defaults(resume=False)
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Required ledger lane; previous fold artifacts are not reused.",
    )
    parser.add_argument(
        "--no-fail-fast",
        dest="fail_fast",
        action="store_false",
        help="Continue after fold failure while preserving BLOCKED evidence.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Explicit canonical Loto7 CSV. Recursive discovery is forbidden.",
    )
    parser.add_argument(
        "--data-access-run-id",
        default=None,
        help="Optional explicit ledger Run ID.",
    )
    return parser


def load_manifest(data_path: Path) -> dict[str, Any]:
    manifest_path = data_path.parent.parent / "data_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FormalBacktestEntrypointError(
            f"immutable data_manifest.json is required: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalBacktestEntrypointError(f"cannot read data manifest: {manifest_path}") from exc
    required = {"canonical_data_sha256", "row_count", "validation_status"}
    missing = sorted(required - set(manifest))
    if missing:
        raise FormalBacktestEntrypointError(f"data manifest is missing required fields: {missing}")
    if manifest["validation_status"] != "PASS":
        raise FormalBacktestEntrypointError(
            f"data manifest validation_status is not PASS: {manifest['validation_status']}"
        )
    canonical_sha = str(manifest["canonical_data_sha256"])
    if len(canonical_sha) != 64 or any(
        character not in "0123456789abcdef" for character in canonical_sha
    ):
        raise FormalBacktestEntrypointError("canonical_data_sha256 is not lowercase SHA-256")
    return manifest


def resolve_data_path(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().absolute()
        if not candidate.is_file() or candidate.is_symlink():
            raise FormalBacktestEntrypointError(
                f"--data must identify a regular, non-symlink file: {candidate}"
            )
        return candidate
    candidates = [
        ROOT / "runs/data-acquisition-loto7/features/canonical_loto7.csv",
        ROOT / "runs/data-acquisition-all/loto7/features/canonical_loto7.csv",
    ]
    found = [item for item in candidates if item.is_file() and not item.is_symlink()]
    if len(found) != 1:
        raise FormalBacktestEntrypointError(
            f"exactly one canonical data path must exist or --data must be supplied; found={found}"
        )
    return found[0]


def require_empty_output(output: Path) -> None:
    output = output.expanduser().absolute()
    for candidate in (output, *output.parents):
        if candidate.exists() and candidate.is_symlink():
            raise FormalBacktestEntrypointError(
                f"output path contains a symlink component: {candidate}"
            )
    if output.exists() and any(output.iterdir()):
        raise FormalBacktestEntrypointError(
            f"instrumented lane requires an empty output directory: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_evidence(
    *, master: Any, manifest: dict[str, Any], data_path: Path
) -> FormalBacktestDatasetEvidence:
    observed_times = tuple(
        value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
        for value in master["draw_date"].tolist()
    )
    return FormalBacktestDatasetEvidence(
        dataset_id="loto7-canonical",
        canonical_sha256=str(manifest["canonical_data_sha256"]),
        source_sha256=source_sha256(data_path),
        game_id="loto7",
        series_ids=tuple(f"n{index}" for index in range(1, 8)),
        observed_times=observed_times,
        draw_ids=tuple(str(item) for item in master["draw_id"].tolist()),
    )


def baselines() -> list[str]:
    return [
        "uniform",
        "random",
        "historical_median",
        "historical_mean",
        "position_median",
        "position_frequency",
        "seasonal_naive",
        "last_value",
        "fixed_optimized_vector",
        "mae_optimal_fixed_vector",
        "plus_minus_1_optimal_fixed_vector",
    ]
