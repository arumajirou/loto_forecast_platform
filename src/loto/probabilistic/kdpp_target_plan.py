from __future__ import annotations

from pathlib import Path

from loto.probabilistic.kdpp_certification_gate import sha256_file, verify_inventory
from loto.probabilistic.kdpp_target_commands import _commands, _runbook
from loto.probabilistic.kdpp_target_contracts import (
    CONTROL_STATUS,
    MODEL_ID,
    SCHEMA_VERSION,
    ControlState,
    TargetExecutionPlan,
    _EXPORTER_FILES,
    _KDPP_FILES,
    _load_object,
    _write_json,
    now_utc,
)
from loto.probabilistic.kdpp_target_repository import (
    _inspect_repository,
    _is_within,
    _recheck_repository,
)


def _write_base_inventory(workspace: Path) -> None:
    paths = ("PLAN.json", "COMMANDS.json", "RUNBOOK.md")
    lines = [f"{sha256_file(workspace / name)}  {name}\n" for name in paths]
    (workspace / "CONTROL_SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def _verify_base_inventory(workspace: Path) -> None:
    verify_inventory(
        workspace,
        "CONTROL_SHA256SUMS",
        {"PLAN.json", "COMMANDS.json", "RUNBOOK.md"},
    )


def prepare_workspace(
    *,
    exporter_repo: Path,
    exporter_head: str,
    exporter_python: Path,
    kdpp_repo: Path,
    kdpp_head: str,
    kdpp_python: Path,
    workspace: Path,
    run_id: str,
    game: str,
    position: int | None,
    prediction_length: int,
    config_sha256: str,
    seed: int = 42,
    samples_per_horizon: int = 128,
    rbf_gamma: float = 1.0,
    quality_pseudocount: float = 0.5,
    psd_tolerance: float = 1e-10,
) -> TargetExecutionPlan:
    workspace = workspace.resolve()
    if workspace.exists():
        raise FileExistsError(workspace)
    exporter_repo = exporter_repo.resolve()
    kdpp_repo = kdpp_repo.resolve()
    if (
        exporter_repo == kdpp_repo
        or _is_within(exporter_repo, kdpp_repo)
        or _is_within(kdpp_repo, exporter_repo)
    ):
        raise ValueError("exporter and k-DPP repositories must be distinct worktrees")
    if _is_within(workspace, exporter_repo) or _is_within(workspace, kdpp_repo):
        raise ValueError("control workspace must be outside both repositories")
    exporter = _inspect_repository(
        exporter_repo,
        role="exporter",
        expected_head=exporter_head,
        python_executable=exporter_python.resolve(),
        required_files=_EXPORTER_FILES,
    )
    kdpp = _inspect_repository(
        kdpp_repo,
        role="kdpp",
        expected_head=kdpp_head,
        python_executable=kdpp_python.resolve(),
        required_files=_KDPP_FILES,
    )
    plan = TargetExecutionPlan(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        status=CONTROL_STATUS,
        run_id=run_id,
        created_at_utc=now_utc(),
        exporter=exporter,
        kdpp=kdpp,
        game=game,
        position=position,
        prediction_length=prediction_length,
        seed=seed,
        samples_per_horizon=samples_per_horizon,
        rbf_gamma=rbf_gamma,
        quality_pseudocount=quality_pseudocount,
        psd_tolerance=psd_tolerance,
        config_sha256=config_sha256,
        source_revision=kdpp.actual_head,
        workspace=str(workspace),
        holdout_opened=False,
        prospective_opened=False,
        automatic_approval=False,
    )
    workspace.mkdir(parents=True)
    (workspace / "events").mkdir()
    _write_json(workspace / "PLAN.json", plan)
    _write_json(workspace / "COMMANDS.json", _commands(plan))
    (workspace / "RUNBOOK.md").write_text(_runbook(plan), encoding="utf-8")
    state = ControlState(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        run_id=run_id,
        current_stage="PREPARED",
        event_count=0,
        last_event_sha256=None,
    )
    _write_json(workspace / "STATE.json", state)
    _write_base_inventory(workspace)
    return plan


def _load_plan(workspace: Path) -> TargetExecutionPlan:
    _verify_base_inventory(workspace)
    plan = TargetExecutionPlan.model_validate(_load_object(workspace / "PLAN.json"))
    if Path(plan.workspace).resolve() != workspace.resolve():
        raise ValueError("plan workspace identity mismatch")
    _recheck_repository(plan.exporter)
    _recheck_repository(plan.kdpp)
    return plan
