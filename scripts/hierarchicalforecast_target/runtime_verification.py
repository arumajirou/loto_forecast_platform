"""Independent verification of runtime artifacts and all forty formal cases."""

from __future__ import annotations

from pathlib import Path

from .constants import (
    EXECUTABLE,
    EXPECTED_STATUS,
    GAMES,
    METHODS,
    PRIMARY,
    REQUIRED,
    TARGET_VERSION,
    CertificationError,
)
from .integrity import (
    checksums,
    finite_number,
    load_json,
    require_directory,
    require_regular_file,
    safe_name,
    sha_file,
    valid_sha256,
    verify_array_evidence,
)


def verify_runtime_files(run_dir: Path, run_id: str) -> None:
    require_directory(run_dir, "runtime run directory")
    entries = list(run_dir.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise CertificationError("runtime run directory contains a symbolic link")
    if {entry.name for entry in entries} != set(REQUIRED):
        raise CertificationError("runtime directory coverage mismatch")
    for name in REQUIRED:
        require_regular_file(run_dir / name, f"runtime artifact {name}")
    for name, digest in checksums(run_dir / "SHA256SUMS", set(PRIMARY)).items():
        if sha_file(run_dir / name) != digest:
            raise CertificationError(f"runtime checksum mismatch: {name}")
    manifest = load_json(run_dir / "ARTIFACT_MANIFEST.json")
    rows = manifest.get("files")
    if manifest.get("run_id") != run_id or not isinstance(rows, list) or len(rows) != 3:
        raise CertificationError("invalid runtime artifact manifest")
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CertificationError("invalid artifact manifest row")
        name = safe_name(str(row.get("path", "")))
        if name in observed:
            raise CertificationError(f"duplicate artifact manifest row: {name}")
        if name not in PRIMARY[:3]:
            raise CertificationError(f"unexpected artifact manifest row: {name}")
        observed.add(name)
        artifact = require_regular_file(run_dir / name, f"manifest artifact {name}")
        if row.get("bytes") != artifact.stat().st_size or row.get("sha256") != sha_file(artifact):
            raise CertificationError(f"artifact manifest mismatch: {name}")
    if observed != set(PRIMARY[:3]):
        raise CertificationError("artifact manifest coverage mismatch")


def _verify_executable(
    result: dict[str, object],
    *,
    game: str,
    method: str,
    n_total: int,
    n_bottom: int,
    horizon: int,
    tolerance: float,
) -> None:
    key = (game, method)
    if result.get("method") != method or result.get("actual_execution") is not True:
        raise CertificationError(f"execution identity evidence missing: {key}")
    if result.get("upstream_version") != TARGET_VERSION or result.get("finite") is not True:
        raise CertificationError(f"version/finite evidence mismatch: {key}")
    if result.get("shape") != [n_total, horizon]:
        raise CertificationError(f"result shape evidence mismatch: {key}")
    coherence = result.get("coherence_error")
    recorded_tolerance = result.get("coherence_tolerance")
    if (
        not finite_number(coherence)
        or not finite_number(recorded_tolerance)
        or float(recorded_tolerance) != tolerance
        or float(coherence) < 0
        or float(coherence) > tolerance
    ):
        raise CertificationError(f"coherence evidence mismatch: {key}")
    verify_array_evidence(
        result.get("bottom"),
        expected_shape=[n_bottom, horizon],
        label=f"{game}/{method}/bottom",
    )
    verify_array_evidence(
        result.get("reconciled"),
        expected_shape=[n_total, horizon],
        label=f"{game}/{method}/reconciled",
    )


def _verify_rejected(result: dict[str, object], *, game: str, method: str) -> None:
    key = (game, method)
    if (
        result.get("method") != method
        or result.get("actual_execution") is not False
        or result.get("hierarchy_is_strict") is not False
        or not isinstance(result.get("error"), str)
        or not str(result.get("error")).strip()
    ):
        raise CertificationError(f"grouped-hierarchy rejection evidence mismatch: {key}")


def verify_cases(
    run_dir: Path,
    run_id: str,
    *,
    horizon: int,
    insample_size: int,
    tolerance: float,
) -> dict[str, int]:
    payload = load_json(run_dir / "METHOD_RESULTS.json")
    rows = payload.get("results")
    if payload.get("run_id") != run_id or not isinstance(rows, list) or len(rows) != 40:
        raise CertificationError("method results must contain exactly 40 rows")
    observed: set[tuple[str, str]] = set()
    hierarchy_by_game: dict[str, tuple[int, int]] = {}
    executed = 0
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            raise CertificationError("method result row must be an object")
        key = (str(row.get("game", "")), str(row.get("method", "")))
        game, method = key
        if game not in GAMES or method not in METHODS or key in observed:
            raise CertificationError(f"invalid or duplicate formal case: {key}")
        observed.add(key)
        expected = EXPECTED_STATUS[method]
        checks = row.get("checks")
        result = row.get("result")
        hierarchy = row.get("hierarchy")
        if row.get("expected_status") != expected or row.get("case_status") != "PASS":
            raise CertificationError(f"formal case state mismatch: {key}")
        if (
            not isinstance(checks, dict)
            or not checks
            or not all(value is True for value in checks.values())
        ):
            raise CertificationError(f"formal checks failed: {key}")
        if not isinstance(result, dict) or result.get("status") != expected:
            raise CertificationError(f"observed status mismatch: {key}")
        if not isinstance(hierarchy, dict):
            raise CertificationError(f"hierarchy evidence missing: {key}")
        n_total = hierarchy.get("n_total")
        n_bottom = hierarchy.get("n_bottom")
        if (
            not isinstance(n_total, int)
            or isinstance(n_total, bool)
            or not isinstance(n_bottom, int)
            or isinstance(n_bottom, bool)
            or n_total <= n_bottom
            or n_bottom <= 0
            or not valid_sha256(hierarchy.get("labels_sha256"))
        ):
            raise CertificationError(f"hierarchy evidence invalid: {key}")
        previous = hierarchy_by_game.setdefault(game, (n_total, n_bottom))
        if previous != (n_total, n_bottom):
            raise CertificationError(f"hierarchy evidence drift within game: {game}")
        if method in EXECUTABLE:
            _verify_executable(
                result,
                game=game,
                method=method,
                n_total=n_total,
                n_bottom=n_bottom,
                horizon=horizon,
                tolerance=tolerance,
            )
            executed += 1
        else:
            _verify_rejected(result, game=game, method=method)
            rejected += 1
    expected_pairs = {(game, method) for game in GAMES for method in METHODS}
    if observed != expected_pairs or executed != 24 or rejected != 16:
        raise CertificationError("formal method/game partition mismatch")
    _verify_input_evidence(
        run_dir,
        run_id,
        hierarchy_by_game,
        horizon=horizon,
        insample_size=insample_size,
    )
    return {"executed_cases": executed, "rejected_cases": rejected}


def _verify_input_evidence(
    run_dir: Path,
    run_id: str,
    hierarchy_by_game: dict[str, tuple[int, int]],
    *,
    horizon: int,
    insample_size: int,
) -> None:
    payload = load_json(run_dir / "INPUT_EVIDENCE.json")
    games = payload.get("games")
    if payload.get("run_id") != run_id or not isinstance(games, dict):
        raise CertificationError("input evidence identity/type mismatch")
    if set(games) != set(GAMES):
        raise CertificationError("input evidence game coverage mismatch")
    for game, row in games.items():
        if not isinstance(row, dict) or not isinstance(row.get("hierarchy"), dict):
            raise CertificationError(f"input hierarchy evidence missing: {game}")
        n_total, n_bottom = hierarchy_by_game[game]
        if row["hierarchy"] != {"n_total": n_total, "n_bottom": n_bottom}:
            raise CertificationError(f"input hierarchy evidence mismatch: {game}")
        evidence = row.get("inputs")
        expected = {
            "base_forecasts",
            "insample_actuals",
            "insample_forecasts",
            "summing_matrix",
        }
        if not isinstance(evidence, dict) or set(evidence) != expected:
            raise CertificationError(f"input array coverage mismatch: {game}")
        verify_array_evidence(
            evidence["base_forecasts"],
            expected_shape=[n_total, horizon],
            label=f"{game}/base_forecasts",
        )
        for name in ("insample_actuals", "insample_forecasts"):
            verify_array_evidence(
                evidence[name],
                expected_shape=[n_total, insample_size],
                label=f"{game}/{name}",
            )
        verify_array_evidence(
            evidence["summing_matrix"],
            expected_shape=[n_total, n_bottom],
            label=f"{game}/summing_matrix",
        )
