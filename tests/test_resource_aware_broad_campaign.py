from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from loto.game.geometry import known_games
from loto.models.catalog_full import build_catalog


def _load_runner_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_resource_aware_broad_campaign.py"
    spec = importlib.util.spec_from_file_location("resource_aware_broad_campaign", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_broad_matrix_expands_model_identities_into_model_game_pairs() -> None:
    module = _load_runner_module()
    catalog = build_catalog()
    games = list(known_games())

    tasks = module._build_tasks(catalog, games)

    assert catalog
    assert len({entry.model_id for entry in catalog}) == len(catalog)
    assert len(games) > 1
    assert len(tasks) == len(catalog) * len(games)
    assert len(tasks) > len(catalog)
    assert len({task.key for task in tasks}) == len(tasks)


def test_timellm_tasks_use_exclusive_gpu_lane() -> None:
    module = _load_runner_module()
    timellm = next(entry for entry in build_catalog() if entry.model_id == "nf-timellm")

    tasks = module._build_tasks([timellm], ["numbers4"])

    assert len(tasks) == 1
    assert tasks[0].resource_class == "EXCLUSIVE_GPU"


def test_campaign_failure_reason_includes_first_seed_failure() -> None:
    module = _load_runner_module()
    summary = {
        "results": [
            {
                "source": "catalog",
                "candidate_id": "nf-dlinear",
                "status": "FAILED",
                "reason": "one or more approved seeds failed",
                "failures": [
                    {
                        "seed": 1,
                        "type": "FileExistsError",
                        "reason": "[Errno 17] File exists: 'lightning_logs/version_1'",
                    }
                ],
            }
        ]
    }

    status, reason = module._campaign_catalog_status(summary, "nf-dlinear")

    assert status == "FAILED"
    assert "one or more approved seeds failed" in reason
    assert "FileExistsError" in reason
    assert "lightning_logs/version_1" in reason


def test_case_result_persists_released_lease_state_and_isolated_cwd(tmp_path, monkeypatch) -> None:
    module = _load_runner_module()
    model = next(entry for entry in build_catalog() if entry.model_id == "sf-autoarima")
    task = module._build_tasks([model], ["numbers4"])[0]
    scheduler = module.ResourceScheduler(
        module.ResourcePolicy(
            max_parallel_cpu_models=1,
            max_parallel_gpu_models=0,
            timeout_seconds=1,
        )
    )
    args = SimpleNamespace(
        resume=False,
        timeout=1,
        timellm_timeout=1,
        synthetic_rows=160,
        seeds="1",
        folds=1,
        test_size=2,
        min_train_size=80,
        holdout_size=4,
        precision="32",
        max_trials=1,
        parallel_trials=1,
        timellm_max_steps=2,
    )
    observed_cwds: list[Path] = []

    def fake_run(*args, **kwargs):
        observed_cwds.append(Path(kwargs["cwd"]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module._run_task(
        task,
        args=args,
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )

    assert result["status"] == "NO_RESULT_FILE"
    assert result["lease"]["released_at"] is not None
    assert observed_cwds
    assert observed_cwds[-1].name == "runtime-workdir"
    assert observed_cwds[-1] == Path(result["runtime_workdir"])
    assert observed_cwds[-1].parent == Path(result["attempt_dir"])

    context_path = Path(result["attempt_dir"]) / "RUNTIME_CONTEXT.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["runtime_workdir"] == result["runtime_workdir"]
    assert context["task_key"] == task.key

    final_path = next((tmp_path / "cases").glob("*/FINAL.json"))
    persisted = json.loads(final_path.read_text(encoding="utf-8"))
    assert persisted["lease"]["released_at"] == result["lease"]["released_at"]
    assert persisted["runtime_workdir"] == result["runtime_workdir"]
