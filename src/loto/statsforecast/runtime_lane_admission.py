from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

TARGET_PACKAGE = "statsforecast"
TARGET_VERSION = "2.1.1"
PYTHON_LANE = "3.13"
_MAX_JSON_BYTES = 16 * 1024 * 1024
_REQUIRED_JSON = {
    "preflight": "/TARGET_HOST_PREFLIGHT.json",
    "target": "/TARGET_HOST_REPORT.json",
    "lane": "/RUNTIME_LANE_REPORT.json",
    "verification": "/VERIFICATION_REPORT.json",
    "matrix": "/MODEL_RUNTIME_MATRIX.json",
    "package": "/PACKAGE_EVIDENCE.json",
    "inventory": "/RUNTIME_INVENTORY.json",
    "config": "/CONFIG.json",
}


def _eq(failures: list[str], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _load_json(bundle: zipfile.ZipFile, suffix: str) -> Any:
    matches = sorted(name for name in bundle.namelist() if name.endswith(suffix))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {suffix!r} member, got {matches}")
    info = bundle.getinfo(matches[0])
    if info.file_size > _MAX_JSON_BYTES:
        raise ValueError(f"JSON member is too large: {matches[0]}")
    try:
        return json.loads(bundle.read(matches[0]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON member {matches[0]}: {exc}") from exc


def _object(payload: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    valid = isinstance(payload, list) and all(isinstance(row, Mapping) for row in payload)
    if not valid:
        raise ValueError("MODEL_RUNTIME_MATRIX.json must be an array of objects")
    return list(payload)


def _special_member_failures(bundle: zipfile.ZipFile) -> list[str]:
    failures = []
    for info in bundle.infolist():
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}:
            failures.append(f"archive member is not a regular file: {info.filename}")
    return failures


def _package_file_failures(files: Any) -> list[str]:
    if not isinstance(files, list) or not files:
        return ["package evidence has no hashed distribution files"]
    failures = []
    for index, item in enumerate(files):
        if not isinstance(item, Mapping):
            failures.append(f"package file {index} is not an object")
            continue
        if not str(item.get("path", "")):
            failures.append(f"package file {index} has no path")
        if not _sha256(item.get("sha256")):
            failures.append(f"package file {index} has invalid SHA-256")
        size = item.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            failures.append(f"package file {index} has invalid size")
    return failures


def _negative_names(
    expected_names: tuple[str, ...],
    supplied: Iterable[str] | None,
) -> frozenset[str]:
    if supplied is not None:
        result = frozenset(map(str, supplied))
    else:
        from .contracts import ExpectedStatus
        from .inventory import model_contract

        result = frozenset(
            name
            for name in expected_names
            if model_contract(name).expected_status is ExpectedStatus.EXPECTED_NEGATIVE_PASS
        )
    unknown = result.difference(expected_names)
    if unknown:
        raise ValueError(f"expected-negative models are outside inventory: {sorted(unknown)}")
    return result


def _model_checks(
    rows: list[Mapping[str, Any]],
    expected_names: tuple[str, ...],
    negative_names: frozenset[str],
) -> tuple[list[str], dict[str, int]]:
    failures: list[str] = []
    names = [str(row.get("model_name", "")) for row in rows]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        failures.append(f"duplicate model rows: {duplicates}")
    if names != list(expected_names):
        failures.append("model order or exact inventory differs from the pinned catalog")
    counts = Counter(str(row.get("status", "UNKNOWN")) for row in rows)
    for row in rows:
        name = str(row.get("model_name", ""))
        negative = name in negative_names
        _eq(
            failures,
            f"model {name} status",
            row.get("status"),
            "EXPECTED_NEGATIVE_PASS" if negative else "VERIFIED",
        )
        _eq(
            failures,
            f"model {name} lifecycle",
            row.get("lifecycle_status"),
            "EXPECTED_NOT_APPLICABLE" if negative else "VERIFIED",
        )
        _eq(failures, f"model {name} finite", row.get("finite"), not negative)
        if negative:
            _eq(
                failures,
                f"model {name} expected status",
                row.get("expected_status"),
                "EXPECTED_NEGATIVE_PASS",
            )
            _eq(
                failures,
                f"model {name} champion eligibility",
                row.get("champion_eligible"),
                False,
            )
        for key, expected in (
            ("shape_ok", True),
            ("identity_ok", True),
            ("series_horizon_ok", True),
            ("duplicate_keys", False),
        ):
            _eq(failures, f"model {name} {key}", row.get(key), expected)
        if "error" in row or "error_type" in row:
            failures.append(f"model {name}: pass row contains error evidence")
    return failures, dict(sorted(counts.items()))


def _final(
    archive: Path,
    package_report: Mapping[str, Any],
    expected_count: int,
    observed_count: int,
    failures: list[str],
    *,
    status_counts: Mapping[str, int] | None = None,
    git_commit: Any = None,
) -> dict[str, Any]:
    passed = not failures
    return {
        "schema_version": 1,
        "status": "ADMITTED" if passed else "REJECTED",
        "decision": "RUNTIME_CERTIFIED" if passed else "MERGE_BLOCKED",
        "formal_pass": passed,
        "archive": str(archive),
        "archive_sha256": package_report.get("archive_sha256"),
        "package_verification": dict(package_report),
        "git_commit": git_commit,
        "expected_model_count": expected_count,
        "observed_model_count": observed_count,
        "status_counts": dict(status_counts or {}),
        "failures": failures,
    }


def inspect_target_host_archive(
    archive: Path | str,
    *,
    package_verifier: Callable[[Path], Mapping[str, Any]] | None = None,
    expected_model_names: Iterable[str] | None = None,
    expected_negative_model_names: Iterable[str] | None = None,
    expected_seed: int = 1,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    archive = Path(archive)
    if package_verifier is None:
        from .runtime_lane_target import verify_target_host_package

        package_verifier = verify_target_host_package
    if expected_model_names is None:
        from .inventory import MODEL_NAMES

        expected_model_names = MODEL_NAMES
    names = tuple(map(str, expected_model_names))
    if not names or len(names) != len(set(names)):
        raise ValueError("expected model names must be non-empty and unique")
    negatives = _negative_names(names, expected_negative_model_names)
    failures: list[str] = []
    package_report = dict(package_verifier(archive))
    if package_report.get("status") != "PASS":
        failures.append(f"outer package verification failed: {package_report.get('failures')}")
        return _final(archive, package_report, len(names), 0, failures)

    try:
        with zipfile.ZipFile(archive) as bundle:
            failures.extend(_special_member_failures(bundle))
            data = {key: _load_json(bundle, suffix) for key, suffix in _REQUIRED_JSON.items()}
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        failures.append(f"archive parse failed: {type(exc).__name__}: {exc}")
        return _final(archive, package_report, len(names), 0, failures)

    preflight = _object(data["preflight"], "TARGET_HOST_PREFLIGHT.json")
    target = _object(data["target"], "TARGET_HOST_REPORT.json")
    lane = _object(data["lane"], "RUNTIME_LANE_REPORT.json")
    verification = _object(data["verification"], "VERIFICATION_REPORT.json")
    package = _object(data["package"], "PACKAGE_EVIDENCE.json")
    inventory = _object(data["inventory"], "RUNTIME_INVENTORY.json")
    config = _object(data["config"], "CONFIG.json")
    rows = _rows(data["matrix"])

    git_head = (preflight.get("git_head") or {}).get("stdout")
    checks = [
        ("preflight status", preflight.get("status"), "PASS"),
        ("Python 3.13", (preflight.get("python") or {}).get("is_python_3_13"), True),
        ("clean worktree", preflight.get("working_tree_clean"), True),
        ("target status", target.get("status"), "PASS"),
        ("target preflight", target.get("preflight_status"), "PASS"),
        ("target error", target.get("error"), None),
        ("target holdout", target.get("holdout_opened"), False),
        ("target actual", target.get("prospective_actual_known"), False),
        ("lane status", lane.get("status"), "PASS"),
        ("lane package", lane.get("target_package"), TARGET_PACKAGE),
        ("lane version", lane.get("target_version"), TARGET_VERSION),
        ("lane Python", lane.get("python_lane"), PYTHON_LANE),
        ("lock return code", lane.get("lock_returncode"), 0),
        ("sync return code", lane.get("sync_returncode"), 0),
        ("certification return code", lane.get("certification_returncode"), 0),
        ("lane holdout", lane.get("holdout_opened"), False),
        ("lane actual", lane.get("prospective_actual_known"), False),
        ("package status", package.get("status"), "VERIFIED"),
        ("package version", package.get("installed_version"), TARGET_VERSION),
        ("inventory status", inventory.get("status"), "VERIFIED"),
        ("inventory complete", inventory.get("complete"), True),
        ("inventory pinned", inventory.get("pinned_count"), len(names)),
        ("inventory exports", inventory.get("runtime_export_count"), len(names)),
        ("inventory available", inventory.get("available_count"), len(names)),
        ("inventory missing", inventory.get("missing"), []),
        ("inventory extra", inventory.get("extra"), []),
        ("runtime export order", inventory.get("runtime_exports"), list(names)),
        ("selected models", config.get("selected_models"), list(names)),
        ("config seed", config.get("seed"), expected_seed),
        ("config n_jobs", config.get("n_jobs"), 1),
        ("config actual", config.get("actual_known"), False),
        ("config lifecycle", config.get("lifecycle"), True),
        ("target seed", target.get("seed"), config.get("seed")),
        ("target horizon", target.get("horizon"), config.get("horizon")),
        ("verification status", verification.get("status"), "VERIFIED"),
        ("formal pass", verification.get("formal_pass"), True),
        ("verification package", verification.get("package_status"), "VERIFIED"),
        ("verification inventory", verification.get("inventory_status"), "VERIFIED"),
        ("selected all", verification.get("selected_all_models"), True),
        ("selected count", verification.get("selected_model_count"), len(names)),
        ("executed count", verification.get("executed_model_count"), len(names)),
        ("lifecycle requested", verification.get("lifecycle_requested"), True),
        ("verification holdout", verification.get("holdout_opened"), False),
        ("verification actual", verification.get("prospective_actual_known"), False),
        ("accuracy claim", verification.get("accuracy_improvement_claimed"), False),
    ]
    for label, actual, expected in checks:
        _eq(failures, label, actual, expected)
    if expected_commit is None:
        failures.append("expected Git commit was not supplied")
    else:
        _eq(failures, "Git commit", git_head, expected_commit)
    if not lane.get("inner_run"):
        failures.append("lane inner runtime path is missing")
    inner_checksum = lane.get("inner_checksum_verification")
    if not isinstance(inner_checksum, Mapping) or inner_checksum.get("status") != "PASS":
        failures.append("lane inner checksum verification is not PASS")
    if target.get("wheelhouse") is not None:
        wheel_report = target.get("wheelhouse_verification")
        if not isinstance(wheel_report, Mapping) or wheel_report.get("status") != "PASS":
            failures.append("target wheelhouse verification is not PASS")
    failures.extend(_package_file_failures(package.get("files")))
    model_failures, status_counts = _model_checks(rows, names, negatives)
    failures.extend(model_failures)
    if verification.get("status_counts") != status_counts:
        failures.append("verification status_counts do not match the model matrix")
    return _final(
        archive,
        package_report,
        len(names),
        len(rows),
        failures,
        status_counts=status_counts,
        git_commit=git_head,
    )


def render_admission_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# StatsForecast runtime admission report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Decision: `{report.get('decision')}`",
        f"- Formal pass: `{str(bool(report.get('formal_pass'))).lower()}`",
        f"- Archive: `{report.get('archive')}`",
        f"- Archive SHA-256: `{report.get('archive_sha256')}`",
        f"- Git commit: `{report.get('git_commit')}`",
        f"- Expected models: `{report.get('expected_model_count', 0)}`",
        f"- Observed models: `{report.get('observed_model_count', 0)}`",
        "",
        "## Status counts",
        "",
    ]
    counts = report.get("status_counts")
    if isinstance(counts, Mapping) and counts:
        lines.extend(f"- `{key}`: {value}" for key, value in sorted(counts.items()))
    else:
        lines.append("- No model status counts were available.")
    lines.extend(["", "## Failures", ""])
    failures = report.get("failures")
    if isinstance(failures, list) and failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def write_admission_artifacts(
    report: Mapping[str, Any],
    output_dir: Path | str,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    json_path = output_dir / "ADMISSION_REPORT.json"
    markdown_path = output_dir / "ADMISSION_REPORT.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_admission_markdown(report), encoding="utf-8")
    rows = []
    for path in (json_path, markdown_path):
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    sums_path = output_dir / "SHA256SUMS"
    sums_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path, "sha256sums": sums_path}


__all__ = [
    "inspect_target_host_archive",
    "render_admission_markdown",
    "write_admission_artifacts",
]
