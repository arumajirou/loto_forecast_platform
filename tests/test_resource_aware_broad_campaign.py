from __future__ import annotations

import importlib.util
import json
import subprocess
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


def _args(**overrides):
    values = {
        "resume": False,
        "timeout": 1,
        "timellm_timeout": 1,
        "synthetic_rows": 160,
        "seeds": "1",
        "folds": 1,
        "test_size": 2,
        "min_train_size": 80,
        "holdout_size": 4,
        "precision": "32",
        "max_trials": 1,
        "parallel_trials": 1,
        "timellm_max_steps": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _normal_termination() -> dict[str, object]:
    return {
        "root_pid": 123,
        "method": "normal-exit",
        "term_sent": False,
        "kill_sent": False,
        "tree_cleanup_complete": True,
    }


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
    args = _args()
    observed_cwds: list[Path] = []

    def fake_run_process(command, *, cwd, env, timeout_seconds):
        observed_cwds.append(Path(cwd))
        return 0, "", "", False, _normal_termination()

    monkeypatch.setattr(module._impl, "_run_process", fake_run_process)
    monkeypatch.setattr(module._impl, "_git_head", lambda: "deadbeef")

    result = module._run_task(
        task,
        args=args,
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )

    assert result["status"] == "NO_RESULT_FILE"
    assert result["lease"]["released_at"] is not None
    assert result["task_fingerprint_sha256"]
    assert observed_cwds
    assert observed_cwds[-1].name == "runtime-workdir"
    assert observed_cwds[-1] == Path(result["runtime_workdir"])
    assert observed_cwds[-1].parent == Path(result["attempt_dir"])

    context_path = Path(result["attempt_dir"]) / "RUNTIME_CONTEXT.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["runtime_workdir"] == result["runtime_workdir"]
    assert context["task_key"] == task.key
    assert context["task_fingerprint_sha256"] == result["task_fingerprint_sha256"]

    final_path = next((tmp_path / "cases").glob("*/FINAL.json"))
    persisted = json.loads(final_path.read_text(encoding="utf-8"))
    assert persisted["lease"]["released_at"] == result["lease"]["released_at"]
    assert persisted["runtime_workdir"] == result["runtime_workdir"]


def test_resume_reuses_only_matching_task_fingerprint(tmp_path, monkeypatch) -> None:
    module = _load_runner_module()
    model = next(entry for entry in build_catalog() if entry.model_id == "sf-autoarima")
    task = module._build_tasks([model], ["numbers4"])[0]
    scheduler = module.ResourceScheduler(
        module.ResourcePolicy(max_parallel_cpu_models=1, max_parallel_gpu_models=0, timeout_seconds=1)
    )
    calls = 0

    def fake_run_process(command, *, cwd, env, timeout_seconds):
        nonlocal calls
        calls += 1
        return 0, "", "", False, _normal_termination()

    monkeypatch.setattr(module._impl, "_run_process", fake_run_process)
    monkeypatch.setattr(module._impl, "_git_head", lambda: "source-head-a")

    first = module._run_task(
        task,
        args=_args(),
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )
    assert calls == 1

    resumed = module._run_task(
        task,
        args=_args(resume=True),
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )
    assert calls == 1
    assert resumed["task_fingerprint_sha256"] == first["task_fingerprint_sha256"]

    changed = module._run_task(
        task,
        args=_args(resume=True, folds=2),
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )
    assert calls == 2
    assert changed["task_fingerprint_sha256"] != first["task_fingerprint_sha256"]
    assert changed["resume_rejected"] is not None
    case_dir = next((tmp_path / "cases").iterdir())
    assert list(case_dir.glob("FINAL.stale-*.json"))


def test_gpu_task_exports_assigned_physical_device(tmp_path, monkeypatch) -> None:
    module = _load_runner_module()
    model = next(entry for entry in build_catalog() if entry.model_id == "nf-dlinear")
    task = module._build_tasks([model], ["numbers4"])[0]
    scheduler = module.ResourceScheduler(
        module.ResourcePolicy(
            max_parallel_cpu_models=1,
            max_parallel_gpu_models=1,
            gpu_device_slots=(0, 1),
            timeout_seconds=1,
        )
    )
    observed_env: dict[str, str] = {}

    def fake_run_process(command, *, cwd, env, timeout_seconds):
        observed_env.update(env)
        return 0, "", "", False, _normal_termination()

    monkeypatch.setattr(module._impl, "_run_process", fake_run_process)
    monkeypatch.setattr(module._impl, "_git_head", lambda: "deadbeef")

    result = module._run_task(
        task,
        args=_args(),
        output_root=tmp_path,
        scheduler=scheduler,
        loto3="loto3",
    )

    assert result["lease"]["gpu_device_index"] == 1
    assert observed_env["CUDA_VISIBLE_DEVICES"] == "1"


def test_timeout_path_invokes_tree_cleanup_before_return(monkeypatch) -> None:
    module = _load_runner_module()
    observed_popen_kwargs: dict[str, object] = {}

    class FakeProcess:
        pid = 4321
        returncode = None

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(["fake"], timeout)
            self.returncode = -15
            return "", ""

        def poll(self):
            return self.returncode

    proc = FakeProcess()

    def fake_popen(*args, **kwargs):
        observed_popen_kwargs.update(kwargs)
        return proc

    cleanup_calls = 0

    def fake_terminate(candidate, *, grace_seconds=5.0):
        nonlocal cleanup_calls
        cleanup_calls += 1
        candidate.returncode = -15
        return {
            "root_pid": candidate.pid,
            "method": "test-tree-cleanup",
            "term_sent": True,
            "kill_sent": False,
            "tree_cleanup_complete": True,
        }

    monkeypatch.setattr(module._impl.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module._impl, "_terminate_process_tree", fake_terminate)

    rc, stdout, stderr, timed_out, termination = module._run_process(
        ["fake"],
        cwd=Path.cwd(),
        env={},
        timeout_seconds=1,
    )

    assert rc is None
    assert timed_out is True
    assert cleanup_calls == 1
    assert termination["tree_cleanup_complete"] is True
    if module.os.name == "posix":
        assert observed_popen_kwargs["start_new_session"] is True


def test_outer_executor_worker_count_never_exceeds_cap() -> None:
    module = _load_runner_module()

    assert module._outer_executor_workers(outer_worker_cap=1, runnable_tasks=20) == 1
    assert module._outer_executor_workers(outer_worker_cap=8, runnable_tasks=20) == 8
    assert module._outer_executor_workers(outer_worker_cap=8, runnable_tasks=3) == 3
