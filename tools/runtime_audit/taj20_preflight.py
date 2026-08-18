from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

EXPECTED_BROAD: Final = 174
EXPECTED_PROBABILISTIC: Final = 76
EXPECTED_UNIFIED: Final = 250
EXPECTED_GAMES: Final = 6
EXPECTED_REUSED_PAIRS: Final = 1044
EXPECTED_INCREMENTAL_PAIRS: Final = 456
EXPECTED_UNIFIED_PAIRS: Final = 1500
EXPECTED_TAJ19_MANIFEST_SHA: Final = (
    "5bee5f8b6825e8f8e202f5af8a67c4c4ed6b76d7d790819261c005859002f1ab"
)
EXPECTED_TAJ19_SHA256SUMS_SHA: Final = (
    "6d8648e838e2ebb2607387db3c8946fca6a0bf7ccff46c93afca809a6ca49bc7"
)
EXPECTED_GAMES_SET: Final = frozenset(
    {"mini", "numbers3", "numbers4", "bingo5", "loto6", "loto7"}
)


class PreflightError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise PreflightError(f"required JSON missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid JSON: {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def verify_sha256sums(root: Path) -> tuple[int, list[str]]:
    path = root / "SHA256SUMS"
    if not path.is_file():
        raise PreflightError(f"TAJ-19 SHA256SUMS missing: {path}")
    checked = 0
    failures: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"invalid SHA256SUMS line {number}")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            failures.append(f"path escapes campaign root: {relative}")
            continue
        if not target.is_file():
            failures.append(f"missing: {relative}")
            continue
        actual = sha256_file(target)
        checked += 1
        if actual != expected:
            failures.append(f"sha mismatch: {relative}")
    return checked, failures


def verify_taj19(campaign: Path) -> dict[str, Any]:
    campaign = campaign.resolve()
    summary = read_json(campaign / "CAMPAIGN_SUMMARY.json")
    if not isinstance(summary, dict):
        raise PreflightError("TAJ-19 CAMPAIGN_SUMMARY must be an object")
    if summary.get("acceptance") != "PASS":
        raise PreflightError(f"TAJ-19 acceptance is not PASS: {summary.get('acceptance')!r}")
    identity = summary.get("identity")
    if not isinstance(identity, dict) or int(identity.get("observed_pairs", -1)) != EXPECTED_REUSED_PAIRS:
        raise PreflightError("TAJ-19 observed pair count is not 1044")
    gates = summary.get("gates")
    if not isinstance(gates, dict) or not gates or not all(bool(value) for value in gates.values()):
        raise PreflightError("TAJ-19 acceptance gates are incomplete or not all true")

    manifest = campaign / "ARTIFACT_MANIFEST.json"
    sums = campaign / "SHA256SUMS"
    actual_manifest_sha = sha256_file(manifest)
    actual_sums_sha = sha256_file(sums)
    if actual_manifest_sha != EXPECTED_TAJ19_MANIFEST_SHA:
        raise PreflightError(
            "TAJ-19 ARTIFACT_MANIFEST identity mismatch: "
            f"{actual_manifest_sha} != {EXPECTED_TAJ19_MANIFEST_SHA}"
        )
    if actual_sums_sha != EXPECTED_TAJ19_SHA256SUMS_SHA:
        raise PreflightError(
            "TAJ-19 SHA256SUMS identity mismatch: "
            f"{actual_sums_sha} != {EXPECTED_TAJ19_SHA256SUMS_SHA}"
        )
    checked, failures = verify_sha256sums(campaign)
    if failures:
        raise PreflightError(f"TAJ-19 source integrity failure: {failures[:10]}")
    return {
        "reuse_status": "PASS",
        "campaign_root": str(campaign),
        "source_head": summary.get("source_head"),
        "reused_pairs": EXPECTED_REUSED_PAIRS,
        "artifact_manifest_sha256": actual_manifest_sha,
        "sha256sums_sha256": actual_sums_sha,
        "source_files_verified": checked,
        "holdout": "CLOSED",
        "prospective": "CLOSED",
        "promotion": "CLOSED",
    }


def verify_identity_plan(identity_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    summary = read_json(identity_root / "IDENTITY_SUMMARY.json")
    unified = read_json(identity_root / "UNIFIED_CATALOG.json")
    native = read_json(identity_root / "PROBABILISTIC_NATIVE.json")
    if not isinstance(summary, dict) or not isinstance(unified, list) or not isinstance(native, list):
        raise PreflightError("identity plan files have invalid top-level types")

    observed = {
        "broad": int(summary.get("broad_catalog_identities", -1)),
        "probabilistic": int(summary.get("probabilistic_catalog_identities", -1)),
        "unified": int(summary.get("unified_catalog_identities", -1)),
        "native": int(summary.get("probabilistic_native_identities", -1)),
        "unified_pairs": int(summary.get("unified_model_game_cross_product", -1)),
    }
    expected = {
        "broad": EXPECTED_BROAD,
        "probabilistic": EXPECTED_PROBABILISTIC,
        "unified": EXPECTED_UNIFIED,
        "native": EXPECTED_PROBABILISTIC,
        "unified_pairs": EXPECTED_UNIFIED_PAIRS,
    }
    if observed != expected:
        raise PreflightError(f"live unified inventory drift: observed={observed} expected={expected}")

    games = [str(value) for value in summary.get("canonical_games", [])]
    if len(games) != EXPECTED_GAMES or frozenset(games) != EXPECTED_GAMES_SET:
        raise PreflightError(f"canonical game drift: {games}")

    model_ids = [str(row.get("model_id", "")) for row in unified if isinstance(row, dict)]
    if len(model_ids) != EXPECTED_UNIFIED or len(set(model_ids)) != EXPECTED_UNIFIED or "" in model_ids:
        raise PreflightError("UNIFIED_CATALOG identities are missing or duplicated")
    broad_rows = [row for row in unified if isinstance(row, dict) and row.get("catalog_source") == "existing"]
    prob_rows = [
        row for row in unified if isinstance(row, dict) and row.get("catalog_source") == "probabilistic"
    ]
    if len(broad_rows) != EXPECTED_BROAD or len(prob_rows) != EXPECTED_PROBABILISTIC:
        raise PreflightError(
            f"unified catalog source counts drifted: broad={len(broad_rows)} probabilistic={len(prob_rows)}"
        )

    prob_ids = {str(row["model_id"]) for row in prob_rows}
    native_ids = {str(row.get("model_id", "")) for row in native if isinstance(row, dict)}
    broad_ids = {str(row["model_id"]) for row in broad_rows}
    if native_ids != prob_ids or len(native_ids) != EXPECTED_PROBABILISTIC:
        raise PreflightError("probabilistic catalog/native identity mismatch")
    collision = sorted(broad_ids & prob_ids)
    if collision:
        raise PreflightError(f"Broad/probabilistic identity collision: {collision}")

    return summary, unified, native


def write_preflight(
    output: Path,
    identity_root: Path,
    taj19_campaign: Path,
) -> dict[str, Any]:
    if output.exists():
        raise PreflightError(f"refusing to overwrite preflight output: {output}")
    output.mkdir(parents=True)

    summary, unified, native = verify_identity_plan(identity_root)
    reuse = verify_taj19(taj19_campaign)
    games = [str(value) for value in summary["canonical_games"]]
    native_by_id = {str(row["model_id"]): row for row in native}
    prob_rows = [row for row in unified if row.get("catalog_source") == "probabilistic"]

    tasks: list[dict[str, Any]] = []
    for row in sorted(prob_rows, key=lambda item: str(item["model_id"])):
        model_id = str(row["model_id"])
        backend = native_by_id[model_id]
        for game in games:
            tasks.append(
                {
                    "task_key": f"{model_id}::{game}",
                    "model_id": model_id,
                    "game": game,
                    "catalog_source": "probabilistic",
                    "primary_backend": backend.get("primary_backend"),
                    "primary_profile": backend.get("primary_profile"),
                    "implementation_kind": backend.get("implementation_kind"),
                    "module": backend.get("module"),
                    "graph_id": backend.get("graph_id"),
                    "runtime_tier": backend.get("runtime_tier"),
                    "status": "PLANNED",
                }
            )
    if len(tasks) != EXPECTED_INCREMENTAL_PAIRS or len({row["task_key"] for row in tasks}) != EXPECTED_INCREMENTAL_PAIRS:
        raise PreflightError("probabilistic incremental matrix is not exactly 456 unique tasks")

    manifest = {
        "schema_version": "taj20-unified-identity-manifest/v1",
        "broad_identities": EXPECTED_BROAD,
        "probabilistic_identities": EXPECTED_PROBABILISTIC,
        "unified_identities": EXPECTED_UNIFIED,
        "games": games,
        "reused_broad_pairs": EXPECTED_REUSED_PAIRS,
        "incremental_probabilistic_pairs": EXPECTED_INCREMENTAL_PAIRS,
        "final_pairs": EXPECTED_UNIFIED_PAIRS,
        "model_ids": sorted(str(row["model_id"]) for row in unified),
    }
    mapping = {
        "schema_version": "taj20-identity-backend-mapping/v1",
        "probabilistic": [native_by_id[key] for key in sorted(native_by_id)],
    }
    final_summary = {
        "schema_version": "taj20-preflight/v1",
        "status": "PASS",
        "identity_contract": {
            "broad": EXPECTED_BROAD,
            "probabilistic": EXPECTED_PROBABILISTIC,
            "unified": EXPECTED_UNIFIED,
            "games": EXPECTED_GAMES,
            "reused_pairs": EXPECTED_REUSED_PAIRS,
            "incremental_pairs": EXPECTED_INCREMENTAL_PAIRS,
            "final_pairs": EXPECTED_UNIFIED_PAIRS,
        },
        "taj19_reuse": reuse,
        "scientific_boundary": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    atomic_json(output / "UNIFIED_IDENTITY_MANIFEST.json", manifest)
    atomic_json(output / "IDENTITY_BACKEND_MAPPING.json", mapping)
    atomic_json(output / "INCREMENTAL_MATRIX_PLAN.json", {"tasks": tasks})
    atomic_json(output / "REUSE_PROVENANCE.json", reuse)
    atomic_json(output / "PRECHECK_SUMMARY.json", final_summary)

    lines: list[str] = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return final_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TAJ-20 unified 250x6 immutable-reuse preflight")
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument("--taj19-campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = write_preflight(
            args.output.resolve(),
            args.identity_root.resolve(),
            args.taj19_campaign.resolve(),
        )
    except PreflightError as exc:
        print("TAJ20_PREFLIGHT=BLOCKED")
        print(f"REASON={exc}")
        print("HOLDOUT=CLOSED")
        print("PROSPECTIVE=CLOSED")
        return 20
    contract = result["identity_contract"]
    reuse = result["taj19_reuse"]
    print("TAJ20_PREFLIGHT=PASS")
    print(f"BROAD_IDENTITIES={contract['broad']}")
    print(f"PROBABILISTIC_IDENTITIES={contract['probabilistic']}")
    print(f"UNIFIED_IDENTITIES={contract['unified']}")
    print(f"GAMES={contract['games']}")
    print(f"TAJ19_REUSED_PAIRS={contract['reused_pairs']}")
    print(f"PROBABILISTIC_INCREMENTAL_PAIRS={contract['incremental_pairs']}")
    print(f"UNIFIED_FINAL_PAIRS={contract['final_pairs']}")
    print(f"TAJ19_SOURCE_FILES_VERIFIED={reuse['source_files_verified']}")
    print(f"TAJ19_ARTIFACT_MANIFEST_SHA256={reuse['artifact_manifest_sha256']}")
    print(f"TAJ19_SHA256SUMS_SHA256={reuse['sha256sums_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
