from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Final

EXPECTED_MODELS: Final = 174
EXPECTED_GAMES: Final = 6
EXPECTED_PAIRS: Final = 1044
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
SUCCESS_STATUSES: Final = frozenset({"SUCCEEDED", "RUNTIME_SMOKE_SUCCEEDED"})
INFRASTRUCTURE_RAW_BLOCKERS: Final = frozenset(
    {"SCHEDULER_ERROR", "POST_RUN_SERIALIZATION_FAILED", "NO_RESULT_FILE"}
)


class AcceptanceError(RuntimeError):
    """Raised when TAJ-19 evidence cannot be accepted."""


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise AcceptanceError(f"required JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_matrix_plan(
    plan: dict[str, Any],
    *,
    expected_models: int,
    expected_games: int,
    expected_pairs: int,
) -> dict[str, Any]:
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise AcceptanceError("MATRIX_PLAN.tasks must be a list of objects")
    model_ids = {str(task.get("model_id", "")) for task in tasks}
    games = {str(task.get("game", "")) for task in tasks}
    if "" in model_ids or "" in games:
        raise AcceptanceError("MATRIX_PLAN contains empty model/game identity")
    task_keys = [f"{task['model_id']}::{task['game']}" for task in tasks]
    duplicate_keys = sorted(key for key, count in Counter(task_keys).items() if count != 1)
    observed = (len(model_ids), len(games), len(tasks), len(set(task_keys)))
    expected = (expected_models, expected_games, expected_pairs, expected_pairs)
    if observed != expected or duplicate_keys:
        raise AcceptanceError(
            "live Broad matrix does not match frozen v1 contract: "
            f"models={len(model_ids)}/{expected_models} games={len(games)}/{expected_games} "
            f"pairs={len(tasks)}/{expected_pairs} unique={len(set(task_keys))}/{expected_pairs} "
            f"duplicates={duplicate_keys[:10]}"
        )
    return {
        "status": "PASS",
        "expected_models": expected_models,
        "observed_models": len(model_ids),
        "expected_games": expected_games,
        "observed_games": len(games),
        "expected_pairs": expected_pairs,
        "observed_pairs": len(tasks),
        "model_ids": sorted(model_ids),
        "games": sorted(games),
        "source_head": plan.get("source_head"),
        "task_key_count": len(task_keys),
    }


def normalize_status(raw: str) -> tuple[str, str | None]:
    value = raw.strip().upper()
    mapping = {
        "SUCCEEDED": "SUCCEEDED",
        "PASS": "SUCCEEDED",
        "ZERO_SHOT_PASS": "SUCCEEDED",
        "RUNTIME_CERTIFIED": "SUCCEEDED",
        "FUNCTIONALLY_CERTIFIED": "SUCCEEDED",
        "RUNTIME_SMOKE_SUCCEEDED": "RUNTIME_SMOKE_SUCCEEDED",
        "FAILED": "FAILED",
        "PREDICT_FAILED": "FAILED",
        "FIT_FAILED": "FAILED",
        "COMMAND_FAILED": "FAILED",
        "GPU_PARTIAL": "FAILED",
        "PREDICTION_MISMATCH": "FAILED",
        "PROVIDER_NOT_IMPLEMENTED": "NOT_ROUTABLE",
        "WORKER_NOT_IMPLEMENTED": "NOT_ROUTABLE",
        "NOT_ROUTABLE": "NOT_ROUTABLE",
        "UNAVAILABLE": "UNAVAILABLE",
        "NOT_AVAILABLE": "UNAVAILABLE",
        "UNSUPPORTED_GAME": "UNSUPPORTED_GAME",
        "NON_STANDALONE_METHOD": "NON_STANDALONE_METHOD",
        "TIMEOUT": "TIMEOUT",
        "BLOCKED_GPU_RESOURCE": "BLOCKED_GPU_RESOURCE",
    }
    if value in mapping:
        return mapping[value], None
    return "FAILED", f"UNMAPPED_RAW_STATUS:{value or '<empty>'}"


def _attempt_dir(campaign_root: Path, value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else (campaign_root / path).resolve()


def functional_evidence(row: dict[str, Any], campaign_root: Path) -> dict[str, Any]:
    normalized = str(row["normalized_status"])
    if normalized not in SUCCESS_STATUSES:
        return {
            "required": False,
            "complete": True,
            "evidence_files": [],
            "reason": "non-success status; success-only functionality gate not applicable",
        }

    attempt = _attempt_dir(campaign_root, row.get("attempt_dir"))
    if attempt is None or not attempt.is_dir():
        return {
            "required": True,
            "complete": False,
            "evidence_files": [],
            "reason": f"attempt directory missing: {attempt}",
        }

    common = [
        attempt / "COMMAND.txt",
        attempt / "RUNTIME_CONTEXT.json",
        attempt / "PROCESS_TERMINATION.json",
        attempt / "stdout.log",
        attempt / "stderr.log",
    ]
    model_id = str(row.get("model_id", ""))
    primary = (
        attempt / "timellm-smoke" / "RESULT.json"
        if model_id == "nf-timellm"
        else attempt / "campaign" / "campaign_summary.json"
    )
    evidence_paths = [*common, primary]
    missing = [str(path) for path in evidence_paths if not path.is_file()]

    process_ok = False
    termination_path = attempt / "PROCESS_TERMINATION.json"
    if termination_path.is_file():
        try:
            process_ok = bool(read_json(termination_path).get("tree_cleanup_complete"))
        except Exception:
            process_ok = False

    primary_ok = False
    if primary.is_file():
        try:
            payload = read_json(primary)
            if model_id == "nf-timellm":
                primary_ok = str(payload.get("status", "")).upper() in {
                    "PASS",
                    "SUCCEEDED",
                    "RUNTIME_SMOKE_SUCCEEDED",
                }
            else:
                rows = payload.get("results", [])
                matches = [
                    item
                    for item in rows
                    if isinstance(item, dict)
                    and item.get("source") == "catalog"
                    and item.get("candidate_id") == model_id
                ]
                primary_ok = len(matches) == 1 and str(matches[0].get("status", "")).upper() in {
                    "PASS",
                    "ZERO_SHOT_PASS",
                    "SUCCEEDED",
                    "RUNTIME_SMOKE_SUCCEEDED",
                    "RUNTIME_CERTIFIED",
                    "FUNCTIONALLY_CERTIFIED",
                }
        except Exception:
            primary_ok = False

    complete = not missing and process_ok and primary_ok
    reasons: list[str] = []
    if missing:
        reasons.append("missing=" + ",".join(missing))
    if not process_ok:
        reasons.append("process termination evidence incomplete")
    if not primary_ok:
        reasons.append("primary runtime evidence is not a unique success")
    return {
        "required": True,
        "complete": complete,
        "evidence_files": [str(path) for path in evidence_paths if path.is_file()],
        "reason": "; ".join(reasons) if reasons else "runtime-success evidence complete",
    }


def verify_existing_sha256s(campaign_root: Path) -> tuple[bool, list[str]]:
    sums_path = campaign_root / "SHA256SUMS"
    if not sums_path.is_file():
        return False, ["campaign SHA256SUMS missing"]
    failures: list[str] = []
    for number, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"invalid SHA256SUMS line {number}")
            continue
        path = campaign_root / relative
        if not path.is_file():
            failures.append(f"missing hashed file: {relative}")
        elif sha256_file(path) != expected:
            failures.append(f"SHA mismatch: {relative}")
    return not failures, failures


def write_final_integrity(campaign_root: Path) -> dict[str, Any]:
    manifest_path = campaign_root / "ARTIFACT_MANIFEST.json"
    sums_path = campaign_root / "SHA256SUMS"
    rows: list[dict[str, Any]] = []
    for path in sorted(campaign_root.rglob("*")):
        if not path.is_file() or path in {manifest_path, sums_path}:
            continue
        rows.append(
            {
                "path": path.relative_to(campaign_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    atomic_json(
        manifest_path,
        {
            "schema_version": "taj19-artifact-manifest/v1",
            "file_count": len(rows),
            "files": rows,
        },
    )
    manifest_sha = sha256_file(manifest_path)
    lines = [f"{row['sha256']}  {row['path']}" for row in rows]
    lines.append(f"{manifest_sha}  ARTIFACT_MANIFEST.json")
    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    final_ok, failures = verify_existing_sha256s(campaign_root)
    if not final_ok:
        raise AcceptanceError(f"final SHA256SUMS verification failed: {failures[:10]}")
    return {
        "manifest_sha256": manifest_sha,
        "sha256sums_sha256": sha256_file(sums_path),
        "file_count": len(rows) + 1,
    }


def verify_campaign(
    campaign_root: Path,
    *,
    expected_models: int,
    expected_games: int,
    expected_pairs: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = read_json(campaign_root / "MATRIX_PLAN.json")
    identity = validate_matrix_plan(
        plan,
        expected_models=expected_models,
        expected_games=expected_games,
        expected_pairs=expected_pairs,
    )
    summary = read_json(campaign_root / "SUMMARY.json")
    results = read_jsonl(campaign_root / "RESULTS.jsonl")
    resource_plan = read_json(campaign_root / "RESOURCE_PLAN.json")
    resource_snapshot = read_json(campaign_root / "RESOURCE_SNAPSHOT.json")
    leases = read_json(campaign_root / "RESOURCE_LEASES.json")

    expected_keys = {f"{task['model_id']}::{task['game']}" for task in plan["tasks"]}
    observed_keys = [str(row.get("task_key", "")) for row in results]
    duplicate_keys = sorted(key for key, count in Counter(observed_keys).items() if count != 1)
    missing_keys = sorted(expected_keys - set(observed_keys))
    unexpected_keys = sorted(set(observed_keys) - expected_keys)

    normalized_rows: list[dict[str, Any]] = []
    raw_counts: Counter[str] = Counter()
    normalized_counts: Counter[str] = Counter()
    unmapped: list[str] = []
    infra_blockers: list[str] = []
    timeout_cleanup_failures: list[str] = []
    success_without_functional_evidence: list[str] = []

    for row in results:
        raw = str(row.get("status", ""))
        normalized, note = normalize_status(raw)
        item = dict(row)
        item.update(raw_status=raw, normalized_status=normalized, normalization_note=note)
        raw_counts[raw] += 1
        normalized_counts[normalized] += 1
        task_key = str(row.get("task_key", ""))
        if note:
            unmapped.append(task_key)
        if raw.upper() in INFRASTRUCTURE_RAW_BLOCKERS:
            infra_blockers.append(task_key)
        termination = row.get("process_termination")
        if normalized == "TIMEOUT" and (
            not isinstance(termination, dict) or not termination.get("tree_cleanup_complete")
        ):
            timeout_cleanup_failures.append(task_key)
        evidence = functional_evidence(item, campaign_root)
        item["functional_evidence"] = evidence
        if normalized in SUCCESS_STATUSES and not evidence["complete"]:
            success_without_functional_evidence.append(task_key)
        normalized_rows.append(item)

    released_leases_ok = isinstance(leases, list) and all(
        isinstance(lease, dict) and lease.get("released_at") is not None for lease in leases
    )
    source_sha_ok, source_sha_failures = verify_existing_sha256s(campaign_root)
    gates = {
        "matrix_plan_exact": identity["status"] == "PASS",
        "summary_expected_pairs": int(summary.get("expected_model_game_pairs", -1)) == expected_pairs,
        "summary_observed_pairs": int(summary.get("observed_model_game_pairs", -1)) == expected_pairs,
        "summary_matrix_complete": summary.get("matrix_complete") is True,
        "result_rows_exact": len(results) == expected_pairs,
        "result_task_keys_unique": not duplicate_keys,
        "no_missing_task_keys": not missing_keys,
        "no_unexpected_task_keys": not unexpected_keys,
        "all_normalized_statuses_valid": not unmapped
        and set(normalized_counts).issubset(NORMALIZED_STATUSES),
        "no_infrastructure_blockers": not infra_blockers,
        "timeout_process_trees_clean": not timeout_cleanup_failures,
        "all_successes_have_functional_evidence": not success_without_functional_evidence,
        "all_resource_leases_released": released_leases_ok,
        "campaign_sha256sums_verified_before_acceptance": source_sha_ok,
        "holdout_closed": summary.get("holdout_evaluated") is False,
        "prospective_closed": summary.get("prospective_evaluated") is False,
        "promotion_closed": summary.get("promotion") is False,
    }
    accepted = all(gates.values())

    surfaces: dict[str, dict[str, Any]] = {}
    for task in plan["tasks"]:
        model_id = str(task["model_id"])
        surface = surfaces.setdefault(
            model_id,
            {
                "model_id": model_id,
                "library": task.get("library"),
                "class_name": task.get("class_name"),
                "resource_class": task.get("resource_class"),
                "games": [],
            },
        )
        surface["games"].append(str(task["game"]))

    atomic_json(campaign_root / "IDENTITY_SUMMARY.json", identity)
    atomic_json(
        campaign_root / "EXECUTION_SURFACES.json",
        {
            "schema_version": "taj19-execution-surfaces/v1",
            "model_count": len(surfaces),
            "surfaces": [
                {**value, "games": sorted(set(value["games"]))}
                for _, value in sorted(surfaces.items())
            ],
            "resource_plan": resource_plan,
            "resource_snapshot": resource_snapshot,
        },
    )
    write_jsonl(campaign_root / "NORMALIZED_RESULTS.jsonl", normalized_rows)
    write_jsonl(
        campaign_root / "FUNCTIONAL_CERTIFICATION.jsonl",
        [
            {
                "task_key": row.get("task_key"),
                "model_id": row.get("model_id"),
                "game": row.get("game"),
                "normalized_status": row["normalized_status"],
                "runtime_success": row["normalized_status"] in SUCCESS_STATUSES,
                "functional_evidence_required": row["functional_evidence"]["required"],
                "functional_evidence_complete": row["functional_evidence"]["complete"],
                "functional_evidence_files": row["functional_evidence"]["evidence_files"],
                "reason": row["functional_evidence"]["reason"],
            }
            for row in normalized_rows
        ],
    )

    campaign_summary = {
        "schema_version": "taj19-broad-runtime-acceptance/v1",
        "issue": "TAJ-19 / GitHub #265",
        "acceptance": "PASS" if accepted else "BLOCKED",
        "source_head": summary.get("source_head"),
        "identity": identity,
        "raw_status_counts": dict(sorted(raw_counts.items())),
        "normalized_status_counts": dict(sorted(normalized_counts.items())),
        "gates": gates,
        "blockers": {
            "duplicate_task_keys": duplicate_keys,
            "missing_task_keys": missing_keys,
            "unexpected_task_keys": unexpected_keys,
            "unmapped_status_task_keys": unmapped,
            "infrastructure_blocker_task_keys": infra_blockers,
            "timeout_cleanup_failure_task_keys": timeout_cleanup_failures,
            "success_without_functional_evidence_task_keys": success_without_functional_evidence,
            "source_sha256_failures": source_sha_failures,
        },
        "scientific_boundary": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    atomic_json(campaign_root / "CAMPAIGN_SUMMARY.json", campaign_summary)
    integrity = write_final_integrity(campaign_root)
    return campaign_summary, integrity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-19 Broad 174x6 acceptance verifier")
    parser.add_argument("mode", choices=("preflight", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-models", type=int, default=EXPECTED_MODELS)
    parser.add_argument("--expected-games", type=int, default=EXPECTED_GAMES)
    parser.add_argument("--expected-pairs", type=int, default=EXPECTED_PAIRS)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    if args.mode == "preflight":
        identity = validate_matrix_plan(
            read_json(root / "MATRIX_PLAN.json"),
            expected_models=args.expected_models,
            expected_games=args.expected_games,
            expected_pairs=args.expected_pairs,
        )
        print("TAJ19_PREFLIGHT=PASS")
        print(f"BROAD_MODELS={identity['observed_models']}")
        print(f"GAMES={identity['observed_games']}")
        print(f"PLANNED_PAIRS={identity['observed_pairs']}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        return 0

    summary, integrity = verify_campaign(
        root,
        expected_models=args.expected_models,
        expected_games=args.expected_games,
        expected_pairs=args.expected_pairs,
    )
    blockers = summary["blockers"]
    print(f"TAJ19_ACCEPTANCE={summary['acceptance']}")
    print(f"EXPECTED_PAIRS={args.expected_pairs}")
    print(f"OBSERVED_PAIRS={summary['identity']['observed_pairs']}")
    print(f"SILENT_SKIP_COUNT={len(blockers['missing_task_keys'])}")
    print(f"DUPLICATE_TASK_KEY_COUNT={len(blockers['duplicate_task_keys'])}")
    print(f"INFRASTRUCTURE_BLOCKER_COUNT={len(blockers['infrastructure_blocker_task_keys'])}")
    print(
        "SUCCESS_WITHOUT_FUNCTIONAL_EVIDENCE="
        + str(len(blockers["success_without_functional_evidence_task_keys"]))
    )
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    print(f"ARTIFACT_MANIFEST_SHA256={integrity['manifest_sha256']}")
    print(f"SHA256SUMS_SHA256={integrity['sha256sums_sha256']}")
    return 0 if summary["acceptance"] == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
