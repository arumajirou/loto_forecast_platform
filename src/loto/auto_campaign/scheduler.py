from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import CampaignConfig
from .data_tracks import DataContract
from .resources import apply_model_resource_profile
from .tasks import CampaignTask


def _worker(
    project_root: str,
    run_root: str,
    frame: pd.DataFrame,
    contract_payload: dict[str, Any],
    config_payload: dict[str, Any],
    task_payload: dict[str, Any],
    num_samples: int,
    smoke: bool,
    fixed_config: dict[str, Any] | None,
) -> dict[str, Any]:
    # Imported inside the worker to avoid a module-level runner/scheduler cycle.
    from .runner import run_task_with_retry

    config = CampaignConfig.model_validate(config_payload)
    contract = DataContract(
        **{
            **contract_payload,
            "number_columns": tuple(contract_payload["number_columns"]),
        }
    )
    task = CampaignTask(**task_payload)
    return run_task_with_retry(
        project_root=Path(project_root),
        run_root=Path(run_root),
        frame=frame,
        contract=contract,
        config=config,
        task=task,
        num_samples=num_samples,
        smoke=smoke,
        fixed_config=fixed_config,
        # Fixed configurations do not need nested Ray Tune. Optuna runs inside
        # the outer Ray task while Ray enforces CPU/GPU concurrency.
        backend_override="optuna",
    )


def run_parallel_fixed_tasks(
    *,
    project_root: Path,
    run_root: Path,
    frame: pd.DataFrame,
    contract: DataContract,
    config: CampaignConfig,
    tasks: list[CampaignTask],
    fixed_configs: dict[str, dict[str, Any]],
    num_samples: int,
    smoke: bool,
    on_result: Callable[[CampaignTask, dict[str, Any]], None],
) -> None:
    if not tasks:
        return

    import ray

    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True, log_to_driver=True)
    frame_ref = ray.put(frame)
    remote_worker = ray.remote(max_retries=0)(_worker)

    pending: dict[Any, CampaignTask] = {}
    task_iterator = iter(tasks)
    max_in_flight = max(1, config.resources.logical_workers)

    def submit(task: CampaignTask) -> None:
        profiled = apply_model_resource_profile(config, task.model_name)
        reference = remote_worker.options(
            num_cpus=profiled.resources.cpus_per_trial,
            num_gpus=profiled.resources.gpus_per_trial,
        ).remote(
            str(project_root),
            str(run_root),
            frame_ref,
            contract.as_dict(),
            profiled.model_dump(mode="python"),
            task.as_dict(),
            num_samples,
            smoke,
            fixed_configs.get(task.key),
        )
        pending[reference] = task

    for _ in range(min(max_in_flight, len(tasks))):
        submit(next(task_iterator))

    while pending:
        ready, _remaining = ray.wait(list(pending), num_returns=1)
        reference = ready[0]
        task = pending.pop(reference)
        try:
            result = ray.get(reference)
        except Exception as exc:
            result = {
                "ok": False,
                "failure": {
                    "task": task.as_dict(),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": ("Ray worker failed before returning a structured result"),
                },
            }
        on_result(task, result)
        try:
            submit(next(task_iterator))
        except StopIteration:
            pass
