from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.moirai2_campaign.target_execution import (  # noqa: E402
    COMMANDS_FILENAME,
    MANIFEST_FILENAME,
    PLAN_FILENAME,
    SHA_FILENAME,
    STATE_FILENAME,
    build_initial_state,
    sha256_file,
    write_json_atomic,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _outside_repo(path: Path) -> bool:
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return True
    return False


def _write_sha256_manifest(root: Path) -> None:
    output = root / SHA_FILENAME
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path != output)
    output.write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}\n" for path in paths),
        encoding="utf-8",
    )


def _write_artifact_manifest(root: Path) -> None:
    files = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name not in {MANIFEST_FILENAME, SHA_FILENAME}
    )
    write_json_atomic(
        root / MANIFEST_FILENAME,
        {
            "schema_version": "moirai2-p8d-control-artifacts-v1",
            "files": files,
            "file_count": len(files),
        },
    )


def _paths(workspace: Path, run_id: str) -> dict[str, str]:
    artifacts = workspace / "artifacts"
    return {
        "supported_candidate": str(artifacts / "lock-candidate" / "supported"),
        "supported_dry_run": str(artifacts / "lock-dry-run" / "supported"),
        "supported_installation": str(artifacts / "lock-install" / "supported"),
        "supported_campaign": str(artifacts / "runtime-campaign" / "supported"),
        "cuda_candidate": str(artifacts / "lock-candidate" / "cuda"),
        "cuda_dry_run": str(artifacts / "lock-dry-run" / "cuda"),
        "cuda_installation": str(artifacts / "lock-install" / "cuda"),
        "cuda_campaign": str(artifacts / "runtime-campaign" / "cuda"),
        "pair_verification": str(artifacts / "runtime-evidence-gate" / run_id),
    }


def _commands(plan: dict[str, Any], control_dir: Path) -> str:
    paths = plan["artifact_paths"]
    snapshot = plan["snapshot_path"]
    run_id = plan["run_id"]
    source_commit = plan["source_identity"]["commit_sha"]
    record = "scripts/record_moirai2_target_execution.py"
    b = "\\"
    supported_candidate = paths["supported_candidate"]
    supported_dry_run = paths["supported_dry_run"]
    supported_installation = paths["supported_installation"]
    supported_campaign = paths["supported_campaign"]
    cuda_candidate = paths["cuda_candidate"]
    cuda_dry_run = paths["cuda_dry_run"]
    cuda_installation = paths["cuda_installation"]
    cuda_campaign = paths["cuda_campaign"]
    pair_verification = paths["pair_verification"]
    lines = [
        "# P8D Target-Host Operator Commands",
        "",
        "These commands are intentionally sequential. Human review is mandatory before each",
        "`--apply` installation. Set lane-specific reviewer variables after review.",
        "",
        "```bash",
        "set -Eeuo pipefail",
        f'CONTROL_DIR="{control_dir}"',
        f'SNAPSHOT="{snapshot}"',
        f'SOURCE_COMMIT="{source_commit}"',
        "",
        "# 1. Supported lock candidate",
        f"uv run python scripts/generate_moirai2_lock_candidate.py {b}",
        f"  --runtime-lane supported-py311 {b}",
        f'  --output-dir "{supported_candidate}" {b}',
        "  --python 3.11",
        f"uv run python {record} record-candidate {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f'  --artifact-dir "{supported_candidate}"',
        "SUPPORTED_LOCK_SHA=\"$(python - <<'PY'",
        "import json",
        (
            "print(json.load(open("
            f'"{supported_candidate}/CANDIDATE_RESULT.json"'
            '))["candidate_lock_sha256"])'
        ),
        "PY",
        ')"',
        "",
        "# 2. Supported dry-run and human-approved install",
        ': "${SUPPORTED_REVIEWER:?Set SUPPORTED_REVIEWER after human review}"',
        ': "${SUPPORTED_REVIEWED_AT:?Set timezone-aware SUPPORTED_REVIEWED_AT}"',
        f"uv run python scripts/install_reviewed_moirai2_lock.py {b}",
        f'  --candidate-dir "{supported_candidate}" {b}',
        f'  --output-dir "{supported_dry_run}" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f'  --reviewer "$SUPPORTED_REVIEWER" {b}',
        f'  --reviewed-at "$SUPPORTED_REVIEWED_AT" {b}',
        f'  --expected-lock-sha256 "$SUPPORTED_LOCK_SHA" {b}',
        "  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK",
        "# Review graph, sources, hashes, warnings, and dry-run before apply.",
        f"uv run python scripts/install_reviewed_moirai2_lock.py {b}",
        f'  --candidate-dir "{supported_candidate}" {b}',
        f'  --output-dir "{supported_installation}" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f'  --reviewer "$SUPPORTED_REVIEWER" {b}',
        f'  --reviewed-at "$SUPPORTED_REVIEWED_AT" {b}',
        f'  --expected-lock-sha256 "$SUPPORTED_LOCK_SHA" {b}',
        f"  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK {b}",
        "  --apply",
        f"uv run python {record} record-installation {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f'  --artifact-dir "{supported_installation}"',
        "",
        "# 3. Supported CPU campaign",
        f"uv run python scripts/run_moirai2_runtime_campaign_p8c.py {b}",
        f"  --campaign-id {run_id}.supported {b}",
        f'  --snapshot-path "$SNAPSHOT" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f"  --device cpu {b}",
        f'  --output-dir "{supported_campaign}"',
        f"uv run python {record} record-campaign {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane supported-py311 {b}",
        f'  --artifact-dir "{supported_campaign}"',
        "",
        "# 4. CUDA lock candidate",
        f"uv run python scripts/generate_moirai2_lock_candidate.py {b}",
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --output-dir "{cuda_candidate}" {b}',
        "  --python 3.11",
        f"uv run python {record} record-candidate {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --artifact-dir "{cuda_candidate}"',
        "CUDA_LOCK_SHA=\"$(python - <<'PY'",
        "import json",
        (
            "print(json.load(open("
            f'"{cuda_candidate}/CANDIDATE_RESULT.json"'
            '))["candidate_lock_sha256"])'
        ),
        "PY",
        ')"',
        "",
        "# 5. CUDA dry-run and human-approved install",
        ': "${CUDA_REVIEWER:?Set CUDA_REVIEWER after independent human review}"',
        ': "${CUDA_REVIEWED_AT:?Set timezone-aware CUDA_REVIEWED_AT}"',
        f"uv run python scripts/install_reviewed_moirai2_lock.py {b}",
        f'  --candidate-dir "{cuda_candidate}" {b}',
        f'  --output-dir "{cuda_dry_run}" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --reviewer "$CUDA_REVIEWER" {b}',
        f'  --reviewed-at "$CUDA_REVIEWED_AT" {b}',
        f'  --expected-lock-sha256 "$CUDA_LOCK_SHA" {b}',
        "  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK",
        "# Review CUDA candidate independently before apply.",
        f"uv run python scripts/install_reviewed_moirai2_lock.py {b}",
        f'  --candidate-dir "{cuda_candidate}" {b}',
        f'  --output-dir "{cuda_installation}" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --reviewer "$CUDA_REVIEWER" {b}',
        f'  --reviewed-at "$CUDA_REVIEWED_AT" {b}',
        f'  --expected-lock-sha256 "$CUDA_LOCK_SHA" {b}',
        f"  --approval-token APPLY-REVIEWED-MOIRAI2-LOCK {b}",
        "  --apply",
        f"uv run python {record} record-installation {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --artifact-dir "{cuda_installation}"',
        "",
        "# 6. CUDA campaign",
        f"uv run python scripts/run_moirai2_runtime_campaign_p8c.py {b}",
        f"  --campaign-id {run_id}.cuda {b}",
        f'  --snapshot-path "$SNAPSHOT" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f"  --device cuda {b}",
        f'  --output-dir "{cuda_campaign}"',
        f"uv run python {record} record-campaign {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f"  --runtime-lane cuda13-experimental {b}",
        f'  --artifact-dir "{cuda_campaign}"',
        "",
        "# 7. Independent pair verification and final recording",
        f"uv run python scripts/verify_moirai2_runtime_evidence.py {b}",
        f'  --supported-campaign-dir "{supported_campaign}" {b}',
        f'  --cuda-campaign-dir "{cuda_campaign}" {b}',
        f'  --expected-source-commit "$SOURCE_COMMIT" {b}',
        f'  --output-dir "{pair_verification}"',
        f"uv run python {record} record-verification {b}",
        f'  --control-dir "$CONTROL_DIR" {b}',
        f'  --artifact-dir "{pair_verification}"',
        "",
        'cat "$CONTROL_DIR/P8D_EXECUTION_STATE.json"',
        'read -r -p "Enterキーで終了します..." _',
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a fail-closed Moirai 2.0 target-host execution workspace"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--snapshot-path", required=True, type=Path)
    parser.add_argument("--workspace-dir", required=True, type=Path)
    arguments = parser.parse_args()
    workspace = arguments.workspace_dir.resolve()
    if workspace.exists():
        raise SystemExit(f"workspace already exists: {workspace}")
    if not _outside_repo(workspace):
        raise SystemExit("workspace must be outside the Git repository")
    snapshot = arguments.snapshot_path.resolve()
    if not snapshot.is_dir():
        raise SystemExit(f"snapshot directory is missing: {snapshot}")
    from loto.moirai2_campaign.runtime_source_identity import (
        capture_source_identity,
    )

    source_identity = capture_source_identity(
        repo_root=REPO_ROOT,
        principal_paths=(
            "scripts/generate_moirai2_lock_candidate.py",
            "scripts/install_reviewed_moirai2_lock.py",
            "scripts/run_moirai2_runtime_campaign_p8c.py",
            "scripts/verify_moirai2_runtime_evidence.py",
            "scripts/prepare_moirai2_target_execution.py",
            "scripts/record_moirai2_target_execution.py",
            "src/loto/moirai2_campaign/target_execution.py",
        ),
    )
    created_at = datetime.now(UTC).isoformat()
    control_dir = workspace / "control"
    control_dir.mkdir(parents=True, exist_ok=False)
    plan = {
        "schema_version": "moirai2-p8d-execution-plan-v1",
        "run_id": arguments.run_id,
        "snapshot_path": str(snapshot),
        "workspace_dir": str(workspace),
        "control_dir": str(control_dir),
        "source_identity": source_identity,
        "artifact_paths": _paths(workspace, arguments.run_id),
        "human_approval_required": True,
        "automatic_approval": False,
        "automatic_installation": False,
        "automatic_runtime_execution": False,
        "stage_order": [
            "supported candidate",
            "supported human-approved installation",
            "supported CPU campaign",
            "CUDA candidate",
            "CUDA human-approved installation",
            "CUDA campaign",
            "independent pair verification",
        ],
        "p9_oof_gate_open_on_pass": True,
        "accuracy_claimed": False,
    }
    state = build_initial_state(
        run_id=arguments.run_id,
        snapshot_path=snapshot,
        source_identity=source_identity,
        created_at=created_at,
    )
    write_json_atomic(control_dir / PLAN_FILENAME, plan)
    write_json_atomic(control_dir / STATE_FILENAME, state)
    (control_dir / COMMANDS_FILENAME).write_text(
        _commands(plan, control_dir),
        encoding="utf-8",
    )
    _write_artifact_manifest(control_dir)
    _write_sha256_manifest(control_dir)
    print(json.dumps(state, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
