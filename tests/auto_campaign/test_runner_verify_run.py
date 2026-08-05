"""Regression test for `verify_run`'s task-manifest discovery.

`verify_run` globs `tasks/**/manifest.json` to find task-level manifests and
checks each one's `trial_persistence.count_match`. That glob also matches the
bundle-internal `best_model/manifest.json` and the per-trial
`trials/trial_*/manifest.json` files, neither of which carries a
`trial_persistence` key by design -- they must not be counted as tasks or
flagged for a missing key that was never theirs to have.
"""

from __future__ import annotations

import json
from pathlib import Path

from loto.auto_campaign.persistence import write_sha256s
from loto.auto_campaign.runner import verify_run


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_nested_bundle_and_trial_manifests_are_not_counted_as_tasks(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    task_dir = run_root / "tasks" / "hpo" / "AutoDLinear" / "u_shared" / "seed_1" / "optuna"

    _write_json(run_root / "manifest.json", {"status": "PASS", "planned_tasks": 1})
    _write_json(
        task_dir / "manifest.json",
        {"status": "PASS", "trial_persistence": {"count_match": True, "failures": []}},
    )
    _write_json(task_dir / "best_model" / "manifest.json", {"status": "PASS"})
    _write_json(task_dir / "trials" / "trial_00000" / "manifest.json", {"status": "PASS"})

    write_sha256s(task_dir / "best_model")
    write_sha256s(task_dir / "trials" / "trial_00000")
    write_sha256s(run_root)

    result = verify_run(run_root)

    assert result["passed_tasks"] == 1
    assert not any("trial count mismatch" in failure for failure in result["failures"])
    assert not any("task count mismatch" in failure for failure in result["failures"])
