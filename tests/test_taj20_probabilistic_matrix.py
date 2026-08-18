from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.run_taj20_probabilistic_matrix import (
    EXPECTED_GAMES,
    EXPECTED_PAIRS,
    EXPECTED_PROBABILISTIC_MODELS,
    Taj20MatrixError,
    read_frozen_plan,
)


def _write_preflight(root: Path) -> None:
    root.mkdir()
    games = [f"game-{index}" for index in range(EXPECTED_GAMES)]
    tasks = [
        {
            "task_key": f"pp-{model:03d}::{game}",
            "model_id": f"pp-{model:03d}",
            "game": game,
            "primary_backend": "builtin",
            "primary_profile": None,
            "status": "PLANNED",
        }
        for model in range(EXPECTED_PROBABILISTIC_MODELS)
        for game in games
    ]
    (root / "PRECHECK_SUMMARY.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "identity_contract": {
                    "probabilistic": EXPECTED_PROBABILISTIC_MODELS,
                    "games": EXPECTED_GAMES,
                    "incremental_pairs": EXPECTED_PAIRS,
                    "final_pairs": 1500,
                    "reused_pairs": 1044,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "INCREMENTAL_MATRIX_PLAN.json").write_text(
        json.dumps({"tasks": tasks}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = []
    for path in sorted(root.iterdir()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_frozen_plan_is_exact_76_by_6(tmp_path: Path) -> None:
    root = tmp_path / "preflight"
    _write_preflight(root)
    frozen = read_frozen_plan(root)
    assert len(frozen["tasks"]) == EXPECTED_PAIRS
    assert len(frozen["model_ids"]) == EXPECTED_PROBABILISTIC_MODELS
    assert len(frozen["games"]) == EXPECTED_GAMES


def test_frozen_plan_rejects_silent_skip(tmp_path: Path) -> None:
    root = tmp_path / "preflight"
    _write_preflight(root)
    plan_path = root / "INCREMENTAL_MATRIX_PLAN.json"
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["tasks"].pop()
    plan_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    lines = []
    for path in sorted(p for p in root.iterdir() if p.name != "SHA256SUMS"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        read_frozen_plan(root)
    except Taj20MatrixError as exc:
        assert "76 x 6" in str(exc)
    else:
        raise AssertionError("silent skip must block TAJ-20 frozen plan")
