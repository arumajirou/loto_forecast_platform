from __future__ import annotations

from pathlib import Path
from typing import Any

from loto.moirai2_campaign.runtime_evidence_case import verify_case
from loto.moirai2_campaign.runtime_evidence_common import (
    CampaignVerification,
    FORMAL_CASE_NAMES,
    RuntimeEvidenceGateError,
    _GIT_OBJECT_PATTERN,
    _SHA256_PATTERN,
    _required_file,
    _safe_relative_path,
    canonical_json_bytes,
    load_json_object,
    sha256_file,
)
from loto.moirai2_campaign.runtime_evidence_manifest import verify_campaign_manifest
from loto.moirai2_campaign.runtime_evidence_prediction import (
    _require_equal,
    _require_true,
)

def _source_identity(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("source_identity")
    if not isinstance(value, dict):
        raise RuntimeEvidenceGateError("campaign source identity is missing")
    if value.get("schema_version") != "moirai2-source-identity-v1":
        raise RuntimeEvidenceGateError("campaign source identity schema differs")
    _require_true(value.get("worktree_clean"), "campaign source worktree was not clean")
    if value.get("changed_paths") != []:
        raise RuntimeEvidenceGateError("campaign source changed_paths is not empty")
    commit_sha = str(value.get("commit_sha", ""))
    tree_sha = str(value.get("tree_sha", ""))
    if not _GIT_OBJECT_PATTERN.fullmatch(commit_sha) or not _GIT_OBJECT_PATTERN.fullmatch(tree_sha):
        raise RuntimeEvidenceGateError("campaign source commit/tree SHA is invalid")
    hashes = value.get("principal_file_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise RuntimeEvidenceGateError("principal source file hashes are missing")
    for relative, digest in hashes.items():
        _safe_relative_path(str(relative))
        if not _SHA256_PATTERN.fullmatch(str(digest)):
            raise RuntimeEvidenceGateError(
                f"principal source file SHA is invalid: {relative}"
            )
    return value


def verify_campaign(
    *,
    campaign_dir: Path,
    expected_runtime_lane: str,
    expected_device: str,
    expected_source_commit: str | None = None,
) -> CampaignVerification:
    root = campaign_dir.resolve()
    if not root.is_dir():
        raise RuntimeEvidenceGateError(f"campaign directory is missing: {root}")
    manifest = verify_campaign_manifest(root)
    config = load_json_object(_required_file(root, "campaign_config.json"))
    summary = load_json_object(_required_file(root, "campaign_summary.json"))
    preflight = load_json_object(_required_file(root, "preflight.json"))
    _require_equal(
        config.get("runtime_lane"),
        expected_runtime_lane,
        "campaign config runtime lane differs",
    )
    _require_equal(config.get("device"), expected_device, "campaign config device differs")
    _require_equal(
        config.get("selected_cases"),
        list(FORMAL_CASE_NAMES),
        "campaign selected cases differ",
    )
    _require_equal(
        config.get("formal_entrypoint"),
        "scripts/run_moirai2_runtime_campaign_p8c.py",
        "campaign formal entrypoint differs",
    )
    _require_equal(
        config.get("execution_policy"),
        "strictly_serial",
        "campaign execution policy differs",
    )
    _require_equal(config.get("parallel_case_count"), 1, "parallel case count differs")
    _require_equal(config.get("prepare_only"), False, "campaign was prepare-only")
    _require_equal(config.get("seed"), 1, "campaign seed differs")
    campaign_id = str(config.get("campaign_id", ""))
    if not campaign_id or "/" in campaign_id or "\\" in campaign_id:
        raise RuntimeEvidenceGateError("campaign_id is invalid")
    source = _source_identity(config)
    launch = load_json_object(_required_file(root, "P8C_LAUNCH_EVIDENCE.json"))
    _require_equal(
        launch.get("schema_version"),
        "moirai2-p8c-launch-evidence-v1",
        "P8C launch evidence schema differs",
    )
    _require_equal(
        launch.get("formal_entrypoint"),
        "scripts/run_moirai2_runtime_campaign_p8c.py",
        "P8C launch entrypoint differs",
    )
    _require_equal(launch.get("return_code"), 0, "P8C campaign return code differs")
    command = launch.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise RuntimeEvidenceGateError("P8C launch command is invalid")
    if not any(item.endswith("run_moirai2_runtime_campaign.py") for item in command):
        raise RuntimeEvidenceGateError("P8C launch command does not use the campaign runner")
    started_ns = int(launch.get("started_at_unix_ns", -1))
    ended_ns = int(launch.get("ended_at_unix_ns", -1))
    if started_ns < 0 or ended_ns < started_ns:
        raise RuntimeEvidenceGateError("P8C launch timestamps are invalid")
    duration = float(launch.get("duration_seconds", -1.0))
    expected_duration = (ended_ns - started_ns) / 1_000_000_000
    if duration < 0 or abs(duration - expected_duration) > 1e-9:
        raise RuntimeEvidenceGateError("P8C launch duration is inconsistent")
    embedded_source = launch.get("source_identity")
    if not isinstance(embedded_source, dict) or canonical_json_bytes(
        embedded_source
    ) != canonical_json_bytes(source):
        raise RuntimeEvidenceGateError("P8C launch source identity differs")
    _require_equal(
        launch.get("campaign_config_sha256"),
        sha256_file(root / "campaign_config.json"),
        "P8C campaign config SHA differs",
    )
    for key, relative in (
        ("stdout_sha256", "p8c_campaign.stdout.log"),
        ("stderr_sha256", "p8c_campaign.stderr.log"),
        ("exit_code_sha256", "p8c_campaign.exit_code.txt"),
    ):
        _require_equal(
            launch.get(key),
            sha256_file(_required_file(root, relative)),
            f"P8C launch {key} differs",
        )
    _require_equal(
        _required_file(root, "p8c_campaign.exit_code.txt").read_text(
            encoding="utf-8"
        ).strip(),
        "0",
        "P8C campaign exit code artifact differs",
    )
    if expected_source_commit is not None:
        _require_equal(
            source.get("commit_sha"),
            expected_source_commit,
            "campaign source commit differs from expected",
        )
    _require_equal(summary.get("status"), "PASS", "campaign summary did not pass")
    _require_true(
        summary.get("formal_runtime_certified"),
        "campaign formal runtime certification is false",
    )
    _require_equal(
        summary.get("runtime_lane"),
        expected_runtime_lane,
        "campaign summary runtime lane differs",
    )
    _require_equal(
        summary.get("requested_device"),
        expected_device,
        "campaign summary requested device differs",
    )
    _require_equal(
        summary.get("required_cases"),
        list(FORMAL_CASE_NAMES),
        "campaign summary required cases differ",
    )
    _require_equal(
        summary.get("observed_cases"),
        list(FORMAL_CASE_NAMES),
        "campaign summary observed cases differ",
    )
    _require_equal(summary.get("failures"), [], "campaign summary contains failures")
    _require_equal(
        summary.get("preflight_status"),
        "PASS",
        "campaign preflight status differs",
    )
    for flag in (
        "accuracy_claimed",
        "oof_opened",
        "holdout_opened",
        "prospective_opened",
    ):
        _require_equal(summary.get(flag), False, f"campaign summary {flag} differs")
    _require_equal(preflight.get("status"), "PASS", "preflight did not pass")
    _require_equal(
        preflight.get("runtime_lane"),
        expected_runtime_lane,
        "preflight runtime lane differs",
    )
    _require_equal(
        preflight.get("requested_device"),
        expected_device,
        "preflight requested device differs",
    )
    lane_evidence = preflight.get("lane_evidence")
    if not isinstance(lane_evidence, dict):
        raise RuntimeEvidenceGateError("preflight lane evidence is missing")
    lock_review = lane_evidence.get("lock_review")
    if not isinstance(lock_review, dict):
        raise RuntimeEvidenceGateError("reviewed lock evidence is missing")
    _require_equal(
        lock_review.get("runtime_lane"),
        expected_runtime_lane,
        "reviewed lock runtime lane differs",
    )
    lock_sha = str(lock_review.get("lock_sha256", ""))
    if not _SHA256_PATTERN.fullmatch(lock_sha):
        raise RuntimeEvidenceGateError("reviewed lock SHA is invalid")
    snapshot_files = lane_evidence.get("snapshot_files")
    if not isinstance(snapshot_files, dict):
        raise RuntimeEvidenceGateError("snapshot file evidence is missing")
    config_sha = str(snapshot_files.get("config.json", ""))
    weight_sha = str(snapshot_files.get("model.safetensors", ""))
    if not _SHA256_PATTERN.fullmatch(config_sha) or not _SHA256_PATTERN.fullmatch(
        weight_sha
    ):
        raise RuntimeEvidenceGateError("snapshot file SHA evidence is invalid")
    cases = tuple(
        verify_case(
            campaign_dir=root,
            case_name=case_name,
            runtime_lane=expected_runtime_lane,
            requested_device=expected_device,
            campaign_id=campaign_id,
        )
        for case_name in FORMAL_CASE_NAMES
    )
    artifact_ids = {
        (case.model_revision, case.config_sha256, case.weight_sha256)
        for case in cases
    }
    if len(artifact_ids) != 1:
        raise RuntimeEvidenceGateError("model artifact identity changes across cases")
    case_artifact = next(iter(artifact_ids))
    _require_equal(
        case_artifact[1],
        config_sha,
        "case model config SHA differs from preflight snapshot",
    )
    _require_equal(
        case_artifact[2],
        weight_sha,
        "case model weight SHA differs from preflight snapshot",
    )
    return CampaignVerification(
        campaign_dir=str(root),
        campaign_id=campaign_id,
        runtime_lane=expected_runtime_lane,
        requested_device=expected_device,
        source_commit=str(source["commit_sha"]),
        source_tree=str(source["tree_sha"]),
        lock_sha256=lock_sha,
        snapshot_config_sha256=config_sha,
        snapshot_weight_sha256=weight_sha,
        manifest=manifest,
        cases=cases,
    )


