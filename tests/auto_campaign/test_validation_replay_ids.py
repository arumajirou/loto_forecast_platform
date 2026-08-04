from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from loto.auto_campaign.contracts import CampaignConfig, CampaignStage
from loto.auto_campaign.persistence import write_json
from loto.auto_campaign.runner import _validation_replay_tasks
from loto.auto_campaign.tasks import CampaignTask


def test_validation_replay_uses_collision_free_trial_indices(
    tmp_path: Path,
) -> None:
    source = tmp_path / "hpo"
    task_root = source / "tasks" / "hpo" / "AutoMLP"
    source_task = CampaignTask(
        stage=CampaignStage.HPO.value,
        model_name="AutoMLP",
        track="u_shared",
        position=None,
        seed=1,
        backend="ray",
    )
    write_json(
        task_root / "manifest.json",
        {"status": "PASS", "task": source_task.as_dict()},
    )
    for name, value in (("trial_a1b2", 1), ("trial_c1d2", 2)):
        trial = task_root / "trials" / name
        trial.mkdir(parents=True)
        (trial / "model.ckpt").write_bytes(b"checkpoint")
        (trial / "config.json").write_text(
            json.dumps({"hidden_size": value}),
            encoding="utf-8",
        )

    config = CampaignConfig(data_path=Path("unused.csv"))
    frame = pd.DataFrame({"row": range(100)})
    tasks, fixed = _validation_replay_tasks(source, frame, config)

    assert {task.config_index for task in tasks} == {0, 1}
    assert len({task.key for task in tasks}) == len(tasks)
    assert len(fixed) == len(tasks)
