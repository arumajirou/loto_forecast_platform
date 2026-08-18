from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Final

EXPECTED_BROAD_MODELS: Final = 174
EXPECTED_PROBABILISTIC_MODELS: Final = 76
EXPECTED_UNIFIED_MODELS: Final = 250
EXPECTED_GAMES: Final = 6
EXPECTED_BROAD_PAIRS: Final = 1044
EXPECTED_PROBABILISTIC_PAIRS: Final = 456
EXPECTED_UNIFIED_PAIRS: Final = 1500
NORMALIZED_STATUSES: Final = frozenset(
    {
        "SUCCEEDED",
        "RUNTIME_SMOKE_SUCCEEDED",
        "FAILED",
        "UNAVAILABLE",
        "NOT_ROUTABLE",
        "UNSUPPORTED_GAME",
        "NON_STANDALONE_METHOD",
        "TIMEOUT",
        "BLOCKED_GPU_RESOURCE",
    }
)
BROAD_REUSE_SENSITIVE_PREFIXES: Final = (
    "src/loto/models/",
    "src/loto/game/",
    "src/loto/orchestration/",
    "src/loto/evaluation/",
)
BROAD_REUSE_SENSITIVE_FILES: Final = frozenset(
    {
        "scripts/run_resource_aware_broad_campaign.py",
        "tools/taj19.sh",
        "tools/taj19-gpu.sh",
        "tools/runtime_audit/taj19_acceptance.py",
        "tools/runtime_audit/taj19_gpu_preflight.py",
        "tools/runtime_audit/taj19_gpu_wait.py",
        "pyproject.toml",
        "uv.lock",
    }
)


class AcceptanceError(RuntimeError):
    """Raised when TAJ-20 unified evidence cannot be accepted."""


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise AcceptanceError(f"required JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise AcceptanceError(f"required JSONL missing: {path}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise AcceptanceError(f"JSONL row {number} is not an object: {path}")
        rows.append(payload)
    return rows


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256s(root: Path) -> tuple[bool, list[str]]:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        return False, [f"SHA256SUMS missing: {root}"]
    failures: list[str] = []
    for number, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"invalid SHA256SUMS line {number}")
            continue
        path = root / relative
        if not path.is_file():
            failures.append(f"missing hashed file: {relative}")
        elif _sha256(path) != expected:
            failures.append(f"SHA mismatch: {relative}")
    return not failures, failures


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AcceptanceError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _broad_reuse_guard(source_head: str) -> dict[str, Any]:
    current_head = _git("rev-parse", "HEAD")
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_head, current_head],
        check=False,
        capture_output=True,
        text=True,
    )
    ancestor = proc.returncode == 0
    changed = (
        _git("diff", "--name-only", f"{source_head}..{current_head}").splitlines()
        if ancestor
        else []
    )
    sensitive = sorted(
        path
        for path in changed
        if path in BROAD_REUSE_SENSITIVE_FILES
        or any(path.startswith(prefix) for prefix in BROAD_REUSE_SENSITIVE_PREFIXES)
    )
    return {
        "source_head": source_head,
        "current_head": current_head,
        "source_is_ancestor": ancestor,
        "changed_paths": changed,
        "sensitive_changed_paths": sensitive,
        "reusable": ancestor and not sensitive,
    }


def _catalog_sets(identity_root: Path) -> tuple[set[str], set[str], set[str], set[str]]:
    summary = _read_json(identity_root / "IDENTITY_SUMMARY.json")
    if (
        int(summary.get("broad_catalog_identities", -1)) != EXPECTED_BROAD_MODELS
        or int(summary.get("probabilistic_catalog_identities", -1))
        != EXPECTED_PROBABILISTIC_MODELS
        or int(summary.get("unified_catalog_identities", -1)) != EXPECTED_UNIFIED_MODELS
        or len(summary.get("canonical_games", [])) != EXPECTED_GAMES
        or int(summary.get("broad_model_game_cross_product", -1)) != EXPECTED_BROAD_PAIRS
        or int(summary.get("unified_model_game_cross_product", -1)) != EXPECTED_UNIFIED_PAIRS
    ):
        raise AcceptanceError(f"identity planner drift: {summary}")
    unified = _read_json(identity_root / "UNIFIED_CATALOG.json")
    native = _read_json(identity_root / "PROBABILISTIC_NATIVE.json")
    if not isinstance(unified, list) or not isinstance(native, list):
        raise AcceptanceError("identity catalog artifacts must be lists")
    broad_ids = {
        str(row.get("model_id", ""))
        for row in unified
        if row.get("catalog_source") == "existing"
    }
    probabilistic_ids = {
        str(row.get("model_id", ""))
        for row in unified
        if row.get("catalog_source") == "probabilistic"
    }
    unified_ids = {str(row.get("model_id", "")) for row in unified}
    native_ids = {str(row.get("model_id", "")) for row in native}
    if "" in unified_ids:
        raise AcceptanceError("unified catalog contains empty model_id")
    if (
        len(broad_ids) != EXPECTED_BROAD_MODELS
        or len(probabilistic_ids) != EXPECTED_PROBABILISTIC_MODELS
    ):
        raise AcceptanceError("unified catalog source counts do not match 174+76")
    if broad_ids & probabilistic_ids:
        raise AcceptanceError(
            "broad/probabilistic model-ID collision: "
            f"{sorted(broad_ids & probabilistic_ids)[:10]}"
        )
    if unified_ids != broad_ids | probabilistic_ids or native_ids != probabilistic_ids:
        raise AcceptanceError("unified/native catalog identity parity failed")
    games = set(map(str, summary["canonical_games"]))
    return broad_ids, probabilistic_ids, unified_ids, games


def _rows_by_expected_matrix(
    rows: list[dict[str, Any]],
    *,
    model_ids: set[str],
    games: set[str],
    expected_pairs: int,
    label: str,
) -> dict[str, Any]:
    keys = [f"{row.get('model_id')}::{row.get('game')}" for row in rows]
    expected = {f"{model_id}::{game}" for model_id in model_ids for game in games}
    duplicate = sorted(key for key, count in Counter(keys).items() if count != 1)
    missing = sorted(expected - set(keys))
    unexpected = sorted(set(keys) - expected)
    invalid_status = sorted(
        key
        for key, row in zip(keys, rows, strict=True)
        if str(row.get("normalized_status")) not in NORMALIZED_STATUSES
    )
    return {
        "label": label,
        "rows": len(rows),
        "expected_pairs": expected_pairs,
        "duplicate_keys": duplicate,
        "missing_keys": missing,
        "unexpected_keys": unexpected,
        "invalid_status_keys": invalid_status,
        "pass": len(rows) == expected_pairs
        and len(expected) == expected_pairs
        and not duplicate
        and not missing
        and not unexpected
        and not invalid_status,
    }


def _write_integrity(root: Path) -> dict[str, str]:
    manifest_path = root / "ARTIFACT_MANIFEST.json"
    sums_path = root / "SHA256SUMS"
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path in {manifest_path, sums_path}:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    _atomic_json(
        manifest_path,
        {"schema_version": "taj20-unified-artifacts/v1", "file_count": len(rows), "files": rows},
    )
    manifest_sha = _sha256(manifest_path)
    lines = [f"{row['sha256']}  {row['path']}" for row in rows]
    lines.append(f"{manifest_sha}  ARTIFACT_MANIFEST.json")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"manifest_sha256": manifest_sha, "sha256sums_sha256": _sha256(sums_path)}


def verify_unified(
    *,
    taj19_root: Path,
    probabilistic_root: Path,
    identity_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, str]]:
    if output_root.exists():
        raise AcceptanceError(f"refusing to reuse TAJ-20 acceptance output: {output_root}")
    output_root.mkdir(parents=True)

    broad_summary = _read_json(taj19_root / "CAMPAIGN_SUMMARY.json")
    probabilistic_summary = _read_json(probabilistic_root / "CAMPAIGN_SUMMARY.json")
    if broad_summary.get("acceptance") != "PASS":
        raise AcceptanceError("TAJ-19 campaign is not accepted")
    if probabilistic_summary.get("acceptance") != "PASS":
        raise AcceptanceError("TAJ-20 probabilistic campaign is not accepted")

    broad_sha_ok, broad_sha_failures = _verify_sha256s(taj19_root)
    probabilistic_sha_ok, probabilistic_sha_failures = _verify_sha256s(probabilistic_root)
    identity_sha_ok, identity_sha_failures = _verify_sha256s(identity_root)

    source_head = str(broad_summary.get("source_head") or "")
    if not source_head:
        raise AcceptanceError("TAJ-19 source_head missing")
    reuse = _broad_reuse_guard(source_head)

    broad_ids, probabilistic_ids, unified_ids, games = _catalog_sets(identity_root)
    broad_rows = _read_jsonl(taj19_root / "NORMALIZED_RESULTS.jsonl")
    probabilistic_rows = _read_jsonl(probabilistic_root / "NORMALIZED_RESULTS.jsonl")
    broad_matrix = _rows_by_expected_matrix(
        broad_rows,
        model_ids=broad_ids,
        games=games,
        expected_pairs=EXPECTED_BROAD_PAIRS,
        label="broad",
    )
    probabilistic_matrix = _rows_by_expected_matrix(
        probabilistic_rows,
        model_ids=probabilistic_ids,
        games=games,
        expected_pairs=EXPECTED_PROBABILISTIC_PAIRS,
        label="probabilistic",
    )
    unified_rows = sorted(
        [*broad_rows, *probabilistic_rows],
        key=lambda row: (str(row.get("model_id")), str(row.get("game"))),
    )
    unified_matrix = _rows_by_expected_matrix(
        unified_rows,
        model_ids=unified_ids,
        games=games,
        expected_pairs=EXPECTED_UNIFIED_PAIRS,
        label="unified",
    )
    gates = {
        "broad_acceptance_pass": broad_summary.get("acceptance") == "PASS",
        "probabilistic_acceptance_pass": probabilistic_summary.get("acceptance") == "PASS",
        "broad_sha256_verified": broad_sha_ok,
        "probabilistic_sha256_verified": probabilistic_sha_ok,
        "identity_sha256_verified": identity_sha_ok,
        "broad_evidence_reusable_from_current_head": bool(reuse["reusable"]),
        "broad_matrix_exact": broad_matrix["pass"],
        "probabilistic_matrix_exact": probabilistic_matrix["pass"],
        "unified_matrix_exact": unified_matrix["pass"],
        "canonical_identity_collision_free": len(unified_ids) == EXPECTED_UNIFIED_MODELS,
        "probabilistic_native_parity": (
            len(probabilistic_ids) == EXPECTED_PROBABILISTIC_MODELS
        ),
        "holdout_closed": broad_summary.get("scientific_boundary", {}).get("holdout") == "CLOSED"
        and probabilistic_summary.get("scientific_boundary", {}).get("holdout") == "CLOSED",
        "prospective_closed": (
            broad_summary.get("scientific_boundary", {}).get("prospective") == "CLOSED"
            and probabilistic_summary.get("scientific_boundary", {}).get("prospective")
            == "CLOSED"
        ),
    }
    accepted = all(gates.values())
    counts = Counter(str(row.get("normalized_status")) for row in unified_rows)
    summary = {
        "schema_version": "taj20-unified-acceptance/v1",
        "issue": "TAJ-20 / GitHub #266",
        "acceptance": "PASS" if accepted else "BLOCKED",
        "identity_counts": {
            "broad": len(broad_ids),
            "probabilistic": len(probabilistic_ids),
            "unified": len(unified_ids),
            "games": len(games),
            "broad_pairs": len(broad_rows),
            "probabilistic_pairs": len(probabilistic_rows),
            "unified_pairs": len(unified_rows),
        },
        "normalized_status_counts": dict(sorted(counts.items())),
        "broad_reuse": reuse,
        "matrix_checks": {
            "broad": broad_matrix,
            "probabilistic": probabilistic_matrix,
            "unified": unified_matrix,
        },
        "gates": gates,
        "blockers": {
            "broad_sha256_failures": broad_sha_failures,
            "probabilistic_sha256_failures": probabilistic_sha_failures,
            "identity_sha256_failures": identity_sha_failures,
            "broad_sensitive_changed_paths": reuse["sensitive_changed_paths"],
        },
        "scientific_boundary": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    _write_jsonl(output_root / "UNIFIED_NORMALIZED_RESULTS.jsonl", unified_rows)
    _atomic_json(output_root / "CAMPAIGN_SUMMARY.json", summary)
    _atomic_json(
        output_root / "EVIDENCE_PROVENANCE.json",
        {
            "taj19_root": str(taj19_root),
            "probabilistic_root": str(probabilistic_root),
            "identity_root": str(identity_root),
            "broad_reuse": reuse,
        },
    )
    integrity = _write_integrity(output_root)
    return summary, integrity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-20 unified 250x6 acceptance verifier")
    parser.add_argument("--taj19-root", type=Path, required=True)
    parser.add_argument("--probabilistic-root", type=Path, required=True)
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary, integrity = verify_unified(
        taj19_root=args.taj19_root.resolve(),
        probabilistic_root=args.probabilistic_root.resolve(),
        identity_root=args.identity_root.resolve(),
        output_root=args.output.resolve(),
    )
    print(f"TAJ20_ACCEPTANCE={summary['acceptance']}")
    print(f"UNIFIED_MODELS={summary['identity_counts']['unified']}")
    print(f"GAMES={summary['identity_counts']['games']}")
    print(f"UNIFIED_PAIRS={summary['identity_counts']['unified_pairs']}")
    broad_reused = str(summary["gates"]["broad_evidence_reusable_from_current_head"]).upper()
    print(f"BROAD_REUSED={broad_reused}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"ARTIFACT_MANIFEST_SHA256={integrity['manifest_sha256']}")
    print(f"SHA256SUMS_SHA256={integrity['sha256sums_sha256']}")
    return 0 if summary["acceptance"] == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
