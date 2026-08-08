"""Fail-closed runtime certification for the optional HierarchicalForecast backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from loto.game.geometry import geometry_for
from loto.reconciliation.hierarchy import (
    Hierarchy,
    UPSTREAM_METHODS,
    build_number_hierarchy,
    reconcile_with_hierarchicalforecast,
)

TARGET_VERSION = "1.5.1"
DEFAULT_GAMES = ("mini", "loto6", "loto7", "bingo5")
EXPECTED_METHOD_STATUS: dict[str, str] = {
    "BottomUp": "VERIFIED",
    "BottomUpSparse": "VERIFIED",
    "TopDown": "UNSUPPORTED_HIERARCHY",
    "TopDownSparse": "UNSUPPORTED_HIERARCHY",
    "MiddleOut": "UNSUPPORTED_HIERARCHY",
    "MiddleOutSparse": "UNSUPPORTED_HIERARCHY",
    "MinTrace": "VERIFIED",
    "MinTraceSparse": "VERIFIED",
    "OptimalCombination": "VERIFIED",
    "ERM": "VERIFIED",
}


class RuntimeCertificationConfig(BaseModel):
    """Validated configuration for one reproducible certification run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_root: Path = Path("artifacts/hierarchicalforecast-runtime")
    games: tuple[str, ...] = DEFAULT_GAMES
    expected_version: str = TARGET_VERSION
    seed: int = Field(default=1, ge=0)
    horizon: int = Field(default=4, ge=1, le=128)
    insample_size: int = Field(default=32, ge=2, le=4096)
    coherence_tolerance: float = Field(default=1e-8, ge=0.0)

    @field_validator("games")
    @classmethod
    def validate_games(cls, games: tuple[str, ...]) -> tuple[str, ...]:
        if not games:
            raise ValueError("games must not be empty")
        if len(games) != len(set(games)):
            raise ValueError("games must not contain duplicates")
        for game in games:
            geometry = geometry_for(game)
            if geometry.family != "select":
                raise ValueError(
                    f"{game}: HierarchicalForecast number hierarchy requires select family"
                )
        return games


@dataclass(frozen=True)
class GeneratedInputs:
    """One immutable synthetic runtime case shared fairly across methods."""

    seed: int
    hierarchy: Hierarchy
    base: np.ndarray
    actuals: np.ndarray
    fitted: np.ndarray
    evidence: dict[str, object]


class DependencyState(BaseModel):
    """Import and version evidence for the optional dependency."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    import_status: str
    installed_version: str | None = None
    module_version: str | None = None
    distribution_version: str | None = None
    version_consistent: bool = False
    module_file: str | None = None
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"hierarchicalforecast-runtime-{stamp}-{os.getpid()}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_sha256(payload: object) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_evidence(values: Any) -> dict[str, object]:
    array = np.asarray(values, dtype=np.float64)
    canonical = np.ascontiguousarray(array.astype("<f8", copy=False))
    finite = bool(np.isfinite(canonical).all())
    evidence: dict[str, object] = {
        "shape": list(canonical.shape),
        "dtype": "float64-le",
        "finite": finite,
        "sha256": _sha256_bytes(canonical.tobytes(order="C")),
    }
    if canonical.size and finite:
        evidence["minimum"] = float(canonical.min())
        evidence["maximum"] = float(canonical.max())
    return evidence


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _array_evidence(value)
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return {"non_finite": repr(value)}
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    _atomic_write_text(path, f"{text}\n")


def _dependency_state() -> DependencyState:
    try:
        import hierarchicalforecast
    except Exception as exc:  # binary/import failures must remain visible
        return DependencyState(
            import_status="FAILED",
            error=f"{type(exc).__name__}: {exc}",
        )

    module_version = str(getattr(hierarchicalforecast, "__version__", "UNKNOWN"))
    try:
        distribution_version = metadata.version("hierarchicalforecast")
    except metadata.PackageNotFoundError:
        distribution_version = None
    installed_version = distribution_version or module_version
    version_consistent = (
        distribution_version is None
        or module_version == "UNKNOWN"
        or module_version == distribution_version
    )
    return DependencyState(
        import_status="PASS",
        installed_version=installed_version,
        module_version=module_version,
        distribution_version=distribution_version,
        version_consistent=version_consistent,
        module_file=str(getattr(hierarchicalforecast, "__file__", "UNKNOWN")),
    )


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def _git_commit() -> str:
    for key in ("GITHUB_SHA", "GIT_COMMIT"):
        value = os.environ.get(key)
        if value:
            return value
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and commit else "UNKNOWN"


def _source_sha256(path: Path) -> str:
    return _sha256_file(path) if path.is_file() else "UNAVAILABLE"


def _build_inputs(
    game: str,
    *,
    seed: int,
    horizon: int,
    insample_size: int,
) -> GeneratedInputs:
    geometry = geometry_for(game)
    hierarchy = build_number_hierarchy(geometry)
    rng = np.random.default_rng(seed)

    bottom = rng.uniform(0.25, 2.0, size=(hierarchy.n_bottom, horizon))
    coherent = hierarchy.summing_matrix @ bottom
    base = coherent.copy()
    aggregate_count = hierarchy.n_total - hierarchy.n_bottom
    base[:aggregate_count] += rng.normal(0.0, 0.25, size=(aggregate_count, horizon))
    base[0] += 0.5

    actual_bottom = rng.uniform(0.25, 2.0, size=(hierarchy.n_bottom, insample_size))
    actuals = hierarchy.summing_matrix @ actual_bottom
    fitted = actuals + rng.normal(0.0, 0.05, size=actuals.shape)

    evidence = {
        "base_forecasts": _array_evidence(base),
        "insample_actuals": _array_evidence(actuals),
        "insample_forecasts": _array_evidence(fitted),
        "summing_matrix": _array_evidence(hierarchy.summing_matrix),
    }
    return GeneratedInputs(
        seed=seed,
        hierarchy=hierarchy,
        base=base,
        actuals=actuals,
        fitted=fitted,
        evidence=evidence,
    )


def _sanitize_result(result: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in result.items():
        if key in {"bottom", "reconciled"} and value is not None:
            sanitized[key] = _array_evidence(value)
        else:
            sanitized[key] = _jsonable(value)
    return sanitized


def _case_checks(
    result: dict[str, object],
    *,
    expected_status: str,
    installed_version: str,
    expected_shape: list[int],
    tolerance: float,
) -> dict[str, bool]:
    checks = {"status_matches": result.get("status") == expected_status}
    if expected_status == "VERIFIED":
        coherence = result.get("coherence_error")
        checks.update(
            {
                "actual_execution": result.get("actual_execution") is True,
                "version_matches_import": result.get("upstream_version") == installed_version,
                "finite": result.get("finite") is True,
                "shape": result.get("shape") == expected_shape,
                "coherence": isinstance(coherence, (int, float))
                and math.isfinite(float(coherence))
                and float(coherence) <= tolerance,
                "reconciled_present": result.get("reconciled") is not None,
                "bottom_present": result.get("bottom") is not None,
            }
        )
    else:
        checks.update(
            {
                "no_execution": result.get("actual_execution") is False,
                "grouped_hierarchy_detected": result.get("hierarchy_is_strict") is False,
            }
        )
    return checks


def _run_case(
    *,
    game: str,
    method: str,
    inputs: GeneratedInputs,
    config: RuntimeCertificationConfig,
    installed_version: str,
) -> dict[str, object]:
    kwargs: dict[str, object] = {}
    if method == "ERM":
        kwargs["insample_actuals"] = inputs.actuals
        kwargs["insample_forecasts"] = inputs.fitted

    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        result = reconcile_with_hierarchicalforecast(
            inputs.base,
            inputs.hierarchy,
            method=method,
            coherence_tolerance=config.coherence_tolerance,
            **kwargs,
        )
    duration_seconds = time.perf_counter() - started
    warning_evidence = [
        {
            "category": warning.category.__name__,
            "message": str(warning.message),
        }
        for warning in captured_warnings
    ]
    expected_status = EXPECTED_METHOD_STATUS[method]
    checks = _case_checks(
        result,
        expected_status=expected_status,
        installed_version=installed_version,
        expected_shape=[inputs.hierarchy.n_total, config.horizon],
        tolerance=config.coherence_tolerance,
    )
    return {
        "game": game,
        "method": method,
        "seed": inputs.seed,
        "duration_seconds": duration_seconds,
        "warnings": warning_evidence,
        "expected_status": expected_status,
        "case_status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "hierarchy": {
            "n_total": inputs.hierarchy.n_total,
            "n_bottom": inputs.hierarchy.n_bottom,
            "labels_sha256": _sha256_bytes("\n".join(inputs.hierarchy.labels).encode("utf-8")),
        },
        "inputs": inputs.evidence,
        "result": _sanitize_result(result),
    }


def _exception_case(
    *,
    game: str,
    method: str,
    inputs: GeneratedInputs,
    exc: Exception,
) -> dict[str, object]:
    return {
        "game": game,
        "method": method,
        "seed": inputs.seed,
        "duration_seconds": None,
        "warnings": [],
        "expected_status": EXPECTED_METHOD_STATUS[method],
        "case_status": "FAIL",
        "checks": {"harness_exception": False},
        "hierarchy": {
            "n_total": inputs.hierarchy.n_total,
            "n_bottom": inputs.hierarchy.n_bottom,
            "labels_sha256": _sha256_bytes("\n".join(inputs.hierarchy.labels).encode("utf-8")),
        },
        "inputs": inputs.evidence,
        "result": {
            "status": "HARNESS_EXCEPTION",
            "actual_execution": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        },
    }


def _runtime_evidence() -> dict[str, object]:
    module_path = Path(__file__).resolve()
    hierarchy_module = sys.modules.get(build_number_hierarchy.__module__)
    hierarchy_source = getattr(hierarchy_module, "__file__", None)
    hierarchy_path = Path(hierarchy_source).resolve() if hierarchy_source else None
    source_sha256 = {
        "runtime_certification": _source_sha256(module_path),
        "hierarchy": (
            _source_sha256(hierarchy_path) if hierarchy_path is not None else "UNAVAILABLE"
        ),
    }
    return {
        "timestamp_utc": _utc_now(),
        "pid": os.getpid(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "device": "cpu",
        "gpu_expected": False,
        "gpu_pid": "NOT_APPLICABLE",
        "cpu_fallback": "NOT_APPLICABLE_CPU_ONLY_LIBRARY",
        "git_commit": _git_commit(),
        "packages": {
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "pydantic": _package_version("pydantic"),
            "hierarchicalforecast": _package_version("hierarchicalforecast"),
        },
        "source_sha256": source_sha256,
        "code_sha256": _canonical_json_sha256(source_sha256),
    }


def _write_artifacts(
    run_dir: Path,
    *,
    certification: dict[str, object],
    method_results: dict[str, object],
    input_evidence: dict[str, object],
) -> None:
    certification_path = run_dir / "RUNTIME_CERTIFICATION.json"
    results_path = run_dir / "METHOD_RESULTS.json"
    inputs_path = run_dir / "INPUT_EVIDENCE.json"
    _write_json(results_path, method_results)
    _write_json(inputs_path, input_evidence)
    _write_json(certification_path, certification)

    primary_paths = (certification_path, results_path, inputs_path)
    manifest = {
        "schema_version": 1,
        "run_id": certification["run_id"],
        "files": [
            {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in primary_paths
        ],
    }
    manifest_path = run_dir / "ARTIFACT_MANIFEST.json"
    _write_json(manifest_path, manifest)

    checksum_paths = (*primary_paths, manifest_path)
    checksums = "".join(f"{_sha256_file(path)}  {path.name}\n" for path in checksum_paths)
    _atomic_write_text(run_dir / "SHA256SUMS", checksums)


def run_certification(config: RuntimeCertificationConfig) -> dict[str, object]:
    """Execute all formal cases and persist evidence even when dependency loading fails."""
    if set(EXPECTED_METHOD_STATUS) != set(UPSTREAM_METHODS):
        raise RuntimeError("method status partition does not match UPSTREAM_METHODS")

    started_at = _utc_now()
    run_id = _run_id()
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    dependency = _dependency_state()
    runtime = _runtime_evidence()

    game_inputs: dict[str, GeneratedInputs] = {}
    for game_index, game in enumerate(config.games):
        game_seed = config.seed + game_index * 10_000
        game_inputs[game] = _build_inputs(
            game,
            seed=game_seed,
            horizon=config.horizon,
            insample_size=config.insample_size,
        )

    method_results: list[dict[str, object]] = []
    if dependency.import_status == "PASS" and dependency.installed_version is not None:
        for game in config.games:
            inputs = game_inputs[game]
            for method in UPSTREAM_METHODS:
                try:
                    case = _run_case(
                        game=game,
                        method=method,
                        inputs=inputs,
                        config=config,
                        installed_version=dependency.installed_version,
                    )
                except Exception as exc:  # persist and continue all remaining cases
                    case = _exception_case(
                        game=game,
                        method=method,
                        inputs=inputs,
                        exc=exc,
                    )
                method_results.append(case)

    passed = sum(result["case_status"] == "PASS" for result in method_results)
    failed = len(method_results) - passed
    expected_cases = len(config.games) * len(UPSTREAM_METHODS)
    exact_version = dependency.installed_version == config.expected_version
    version_consistent = dependency.version_consistent

    if dependency.import_status != "PASS":
        status = "BLOCKED_DEPENDENCY"
    elif not exact_version or not version_consistent:
        status = "FAILED_VERSION_MISMATCH"
    elif len(method_results) != expected_cases or failed:
        status = "FAILED_RUNTIME"
    else:
        status = "VERIFIED"

    method_payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "results": method_results,
    }
    config_payload = config.model_dump(mode="json")
    unique_inputs = {
        game: {
            "seed": game_inputs[game].seed,
            "hierarchy": {
                "n_total": game_inputs[game].hierarchy.n_total,
                "n_bottom": game_inputs[game].hierarchy.n_bottom,
            },
            "inputs": game_inputs[game].evidence,
        }
        for game in config.games
    }
    input_payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "games": unique_inputs,
    }
    certification: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "formal_success": status == "VERIFIED",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "run_directory": str(run_dir),
        "config": config_payload,
        "config_sha256": _canonical_json_sha256(config_payload),
        "data_sha256": _canonical_json_sha256(unique_inputs),
        "dependency": dependency.model_dump(mode="json"),
        "runtime": runtime,
        "summary": {
            "expected_cases": expected_cases,
            "executed_cases": len(method_results),
            "passed_cases": passed,
            "failed_cases": failed,
            "exact_version_match": exact_version,
            "module_distribution_version_consistent": version_consistent,
        },
        "certification_boundaries": {
            "forecast_accuracy": "NOT_EVALUATED",
            "holdout": "NOT_EVALUATED",
            "prospective": "NOT_EVALUATED",
            "gpu": "NOT_APPLICABLE_CPU_ONLY_RECONCILIATION",
        },
    }
    _write_artifacts(
        run_dir,
        certification=certification,
        method_results=method_payload,
        input_evidence=input_payload,
    )
    return certification


def _parse_games(value: str) -> tuple[str, ...]:
    if value.strip().lower() == "all":
        return DEFAULT_GAMES
    return tuple(part.strip() for part in value.split(",") if part.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Certify the installed HierarchicalForecast runtime and persist evidence.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/hierarchicalforecast-runtime"),
    )
    parser.add_argument("--games", default="all")
    parser.add_argument("--expected-version", default=TARGET_VERSION)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--insample-size", type=int, default=32)
    parser.add_argument("--coherence-tolerance", type=float, default=1e-8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RuntimeCertificationConfig(
        output_root=args.output_root,
        games=_parse_games(args.games),
        expected_version=args.expected_version,
        seed=args.seed,
        horizon=args.horizon,
        insample_size=args.insample_size,
        coherence_tolerance=args.coherence_tolerance,
    )
    result = run_certification(config)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
