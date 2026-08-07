from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"
EXPECTED_CONFIG_SHA256 = "173dd40c0a7e08a71b660110fd6334ee85eb9f6ce6f30df0a6cbaea3bb1ff3b4"
EXPECTED_GENERATION_CONFIG_SHA256 = (
    "d90f7f1d9ef012f9ec0bd76fdf42e6979d086f157d65910b3b273edfb100e748"
)
EXPECTED_WEIGHT_SHA256 = {
    "model.safetensors": "414435b508391f92afadd2aaeec418c806776aeccbce12e638d73a139ca5ca78"
}
EXPECTED_REMOTE_CODE_SHA256 = {
    "configuration_sundial.py": (
        "1a79b4265d7a7feabb1fadc336c2c7580157ededd7cc58655f007213447eb7e4"
    ),
    "flow_loss.py": "fb33d3c3988015124c9f4e05728127d85afee8b416930c0e6d5097e4ced2ecf8",
    "modeling_sundial.py": (
        "4a7ce7defa6578d0ae84593587d164afb933cfa6e52aee53f709f236b00b85e4"
    ),
    "ts_generation_mixin.py": (
        "789577dafbd9605d4c1b2d8930ff2861277090b004b6e7ddef6011b79444942e"
    ),
}
EXPECTED_CASES = (
    "cpu-smoke-ns001",
    "cuda-ns001",
    "cuda-ns003",
    "cuda-ns020",
    "cuda-ns050",
    "cuda-ns100",
    "cuda-replay-a",
    "cuda-replay-b",
)


class SemanticVerificationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticVerificationError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SemanticVerificationError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def quantile_key(level: float) -> str:
    return f"q{level:.6f}".rstrip("0").rstrip(".")


def resolve_snapshot(snapshot: Path | None, run_dir: Path | None) -> Path:
    if snapshot is not None:
        return snapshot.expanduser().resolve()
    if run_dir is None:
        raise SemanticVerificationError("snapshot or run directory is required")
    environment = load_json(run_dir / "environment.json")
    snapshot_evidence = environment.get("snapshot")
    if not isinstance(snapshot_evidence, dict) or not snapshot_evidence.get("snapshot_path"):
        raise SemanticVerificationError("environment snapshot_path is missing")
    return Path(str(snapshot_evidence["snapshot_path"])).expanduser().resolve()


def verify_snapshot(snapshot: Path, repo_root: Path | None) -> list[str]:
    reasons: list[str] = []
    if not snapshot.is_dir() or snapshot.name != REVISION:
        return ["SNAPSHOT_IDENTITY_MISMATCH"]
    expected_files = {
        "config.json": EXPECTED_CONFIG_SHA256,
        "generation_config.json": EXPECTED_GENERATION_CONFIG_SHA256,
        **EXPECTED_WEIGHT_SHA256,
        **EXPECTED_REMOTE_CODE_SHA256,
    }
    for name, expected_hash in expected_files.items():
        path = snapshot / name
        if not path.is_file():
            reasons.append(f"SNAPSHOT_FILE_MISSING:{name}")
        elif sha256(path) != expected_hash:
            reasons.append(f"SNAPSHOT_HASH_MISMATCH:{name}")
    weight_names = {
        path.name
        for pattern in ("*.safetensors", "*.bin")
        for path in snapshot.glob(pattern)
    }
    if weight_names != set(EXPECTED_WEIGHT_SHA256):
        reasons.append("SNAPSHOT_WEIGHT_SET_MISMATCH")
    runtime_remote_names = {path.name for path in snapshot.glob("*.py")}
    if runtime_remote_names != set(EXPECTED_REMOTE_CODE_SHA256):
        reasons.append("SNAPSHOT_REMOTE_CODE_SET_MISMATCH")
    if repo_root is not None:
        probe_path = repo_root / "audit/tsfm-runtime/sundial-base/snapshot-probe.json"
        try:
            probe = load_json(probe_path)
        except SemanticVerificationError:
            reasons.append("PINNED_SNAPSHOT_PROBE_MISSING_OR_INVALID")
        else:
            if probe.get("repo_id") != REPO_ID or probe.get("revision") != REVISION:
                reasons.append("PINNED_SNAPSHOT_PROBE_IDENTITY_MISMATCH")
            if probe.get("weight_sha256") != EXPECTED_WEIGHT_SHA256["model.safetensors"]:
                reasons.append("PINNED_SNAPSHOT_PROBE_WEIGHT_MISMATCH")
            if probe.get("config_sha256") != EXPECTED_CONFIG_SHA256:
                reasons.append("PINNED_SNAPSHOT_PROBE_CONFIG_MISMATCH")
    return reasons


def as_finite_array(value: Any, shape: tuple[int, ...], label: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise SemanticVerificationError(f"{label} is not numeric") from exc
    if array.shape != shape:
        raise SemanticVerificationError(
            f"{label} shape mismatch: expected={shape}, actual={array.shape}"
        )
    if not np.isfinite(array).all():
        raise SemanticVerificationError(f"{label} contains non-finite values")
    return array


def arrays_match(actual: Any, expected: np.ndarray, shape: tuple[int, ...]) -> bool:
    try:
        candidate = as_finite_array(actual, shape, "candidate")
    except SemanticVerificationError:
        return False
    return bool(np.allclose(candidate, expected, rtol=0.0, atol=1e-9))


def verify_response(response: dict[str, Any], expected_snapshot: Path) -> list[str]:
    reasons: list[str] = []
    if response.get("status") != "OK" or response.get("provider_version") != 2:
        return ["RESPONSE_STATUS_OR_VERSION_MISMATCH"]
    if response.get("repo_id") != REPO_ID or response.get("revision") != REVISION:
        reasons.append("RESPONSE_IDENTITY_MISMATCH")
    try:
        response_snapshot = Path(str(response.get("snapshot_path", ""))).resolve()
    except OSError:
        response_snapshot = Path("/")
    if response_snapshot != expected_snapshot:
        reasons.append("RESPONSE_SNAPSHOT_PATH_MISMATCH")
    shape_value = response.get("samples_shape")
    if not isinstance(shape_value, list) or len(shape_value) != 3:
        return [*reasons, "SAMPLE_SHAPE_METADATA_INVALID"]
    try:
        shape = tuple(int(value) for value in shape_value)
    except (TypeError, ValueError):
        return [*reasons, "SAMPLE_SHAPE_METADATA_INVALID"]
    if shape[0] != 7 or shape[2] != 1 or shape[1] < 1 or shape[1] > 100:
        reasons.append("SAMPLE_SHAPE_CONTRACT_MISMATCH")
    try:
        samples = as_finite_array(response.get("samples"), shape, "samples")
    except SemanticVerificationError as exc:
        return [*reasons, f"SAMPLES_INVALID:{exc}"]
    expected_matrix_shape = (7, 1)
    expected_statistics = {
        "mean": np.mean(samples, axis=1),
        "median": np.median(samples, axis=1),
        "std": np.std(samples, axis=1, ddof=0),
    }
    statistics = response.get("sample_statistics")
    if not isinstance(statistics, dict):
        reasons.append("SAMPLE_STATISTICS_MISSING")
    else:
        for name, expected in expected_statistics.items():
            if not arrays_match(statistics.get(name), expected, expected_matrix_shape):
                reasons.append(f"SAMPLE_STATISTIC_MISMATCH:{name}")
    point_forecasts = response.get("point_forecasts")
    if not isinstance(point_forecasts, dict):
        reasons.append("POINT_FORECASTS_MISSING")
    else:
        for name in ("mean", "median"):
            if not arrays_match(
                point_forecasts.get(name),
                expected_statistics[name],
                expected_matrix_shape,
            ):
                reasons.append(f"POINT_FORECAST_MISMATCH:{name}")
    levels_value = response.get("quantile_levels")
    if not isinstance(levels_value, list) or not levels_value:
        reasons.append("QUANTILE_LEVELS_MISSING")
        levels: tuple[float, ...] = ()
    else:
        try:
            levels = tuple(float(value) for value in levels_value)
        except (TypeError, ValueError):
            levels = ()
            reasons.append("QUANTILE_LEVELS_INVALID")
    if levels and (
        any(not math.isfinite(level) or not 0.0 <= level <= 1.0 for level in levels)
        or any(left >= right for left, right in zip(levels, levels[1:], strict=False))
    ):
        reasons.append("QUANTILE_LEVELS_INVALID")
    quantiles = response.get("quantiles")
    expected_keys = [quantile_key(level) for level in levels]
    if not isinstance(quantiles, dict) or list(quantiles) != expected_keys:
        reasons.append("QUANTILE_KEYS_MISMATCH")
    elif levels:
        expected_quantiles = np.quantile(samples, levels, axis=1)
        for index, key in enumerate(expected_keys):
            if not arrays_match(
                quantiles.get(key),
                expected_quantiles[index],
                expected_matrix_shape,
            ):
                reasons.append(f"QUANTILE_VALUE_MISMATCH:{key}")
    if response.get("quantile_source") != "EMPIRICAL_FROM_GENERATED_SAMPLES":
        reasons.append("QUANTILE_SOURCE_MISMATCH")
    strategy = response.get("point_strategy")
    if strategy not in {"mean", "median"}:
        reasons.append("POINT_STRATEGY_INVALID")
    else:
        expected_predictions = expected_statistics[strategy][:, 0]
        if not arrays_match(response.get("predictions"), expected_predictions, (7,)):
            reasons.append("SELECTED_POINT_MISMATCH")
    if response.get("prediction_shape") != [7] or response.get("finite") is not True:
        reasons.append("LEGACY_POINT_METADATA_MISMATCH")
    properties = response.get("properties")
    if not isinstance(properties, dict):
        reasons.append("PROPERTIES_MISSING")
    else:
        if properties.get("config_sha256") != EXPECTED_CONFIG_SHA256:
            reasons.append("PROPERTY_CONFIG_HASH_MISMATCH")
        if properties.get("weight_sha256") != EXPECTED_WEIGHT_SHA256:
            reasons.append("PROPERTY_WEIGHT_HASH_MISMATCH")
        if properties.get("remote_code_sha256") != EXPECTED_REMOTE_CODE_SHA256:
            reasons.append("PROPERTY_REMOTE_CODE_HASH_MISMATCH")
        if properties.get("num_samples") != shape[1]:
            reasons.append("PROPERTY_SAMPLE_COUNT_MISMATCH")
        if properties.get("quantile_levels") != list(levels):
            reasons.append("PROPERTY_QUANTILE_LEVELS_MISMATCH")
        if properties.get("point_strategy") != strategy:
            reasons.append("PROPERTY_POINT_STRATEGY_MISMATCH")
    artifact = response.get("artifact_reference")
    if not isinstance(artifact, dict):
        reasons.append("ARTIFACT_REFERENCE_MISSING")
    else:
        if artifact.get("repo_id") != REPO_ID or artifact.get("revision") != REVISION:
            reasons.append("ARTIFACT_REFERENCE_IDENTITY_MISMATCH")
        if Path(str(artifact.get("snapshot_path", ""))).resolve() != expected_snapshot:
            reasons.append("ARTIFACT_REFERENCE_SNAPSHOT_MISMATCH")
    return reasons


def verify_run(run_dir: Path, snapshot: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    summary = load_json(run_dir / "certification-summary.json")
    cases = summary.get("cases")
    reasons: list[str] = []
    if not isinstance(cases, list):
        return {
            "status": "FAIL",
            "reasons": ["CASES_MISSING"],
            "case_results": {},
        }
    names = [str(case.get("name", "")) for case in cases if isinstance(case, dict)]
    if tuple(names) != EXPECTED_CASES:
        reasons.append("CASE_MATRIX_MISMATCH")
    case_results: dict[str, list[str]] = {}
    for name in names:
        response_path = run_dir / "cases" / name / "response.json"
        try:
            response = load_json(response_path)
            case_reasons = verify_response(response, snapshot)
        except SemanticVerificationError as exc:
            case_reasons = [f"RESPONSE_INVALID:{exc}"]
        case_results[name] = case_reasons
        reasons.extend(f"{name}:{reason}" for reason in case_reasons)
    return {
        "status": "PASS" if not reasons else "FAIL",
        "reasons": reasons,
        "case_results": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Sundial v2 snapshot and response semantics"
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/sundial-provider-v2-semantic-verification"),
    )
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve() if args.run_dir else None
    snapshot = resolve_snapshot(args.snapshot, run_dir)
    snapshot_reasons = verify_snapshot(
        snapshot,
        args.repo_root.expanduser().resolve() if args.repo_root else None,
    )
    run_report: dict[str, Any] | None = None
    if not args.snapshot_only:
        if run_dir is None:
            raise SemanticVerificationError(
                "run directory is required unless --snapshot-only is set"
            )
        run_report = verify_run(run_dir, snapshot)
    reasons = list(snapshot_reasons)
    if run_report is not None:
        reasons.extend(run_report["reasons"])
    status = "PASS" if not reasons else "FAIL"
    report = {
        "schema_version": 1,
        "verified_at_utc": utc_now(),
        "status": status,
        "snapshot": str(snapshot),
        "snapshot_reasons": snapshot_reasons,
        "run_dir": str(run_dir) if run_dir else None,
        "run_report": run_report,
        "reasons": reasons,
    }
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    suffix = "snapshot" if args.snapshot_only else (run_dir.name if run_dir else "run")
    output_path = output_root / f"{suffix}.json"
    write_json(output_path, report)
    print(f"SUNDIAL_PROVIDER_V2_SEMANTIC_VERIFICATION={status}")
    print(f"SEMANTIC_REPORT={output_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SemanticVerificationError as exc:
        print(f"SUNDIAL_PROVIDER_V2_SEMANTIC_VERIFICATION=BLOCKED\nREASON={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
