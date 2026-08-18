from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_audit" / "taj19_acceptance.py"
LAUNCHER = ROOT / "tools" / "taj19.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("taj19_acceptance", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_campaign(tmp_path: Path, *, rows: list[dict] | None = None) -> Path:
    module = load_module()
    root = tmp_path / "campaign"
    root.mkdir()
    tasks = [
        {
            "ordinal": 1,
            "model_id": "m1",
            "library": "lib1",
            "class_name": "M1",
            "game": "g1",
            "resource_class": "CPU",
        },
        {
            "ordinal": 2,
            "model_id": "m1",
            "library": "lib1",
            "class_name": "M1",
            "game": "g2",
            "resource_class": "CPU",
        },
        {
            "ordinal": 3,
            "model_id": "m2",
            "library": "lib2",
            "class_name": "M2",
            "game": "g1",
            "resource_class": "GPU",
        },
        {
            "ordinal": 4,
            "model_id": "m2",
            "library": "lib2",
            "class_name": "M2",
            "game": "g2",
            "resource_class": "GPU",
        },
    ]
    write_json(
        root / "MATRIX_PLAN.json",
        {
            "source_head": "abc",
            "catalog_models": 2,
            "games": ["g1", "g2"],
            "model_game_pairs": 4,
            "tasks": tasks,
        },
    )
    if rows is None:
        rows = [
            {
                "ordinal": task["ordinal"],
                "task_key": f"{task['model_id']}::{task['game']}",
                "model_id": task["model_id"],
                "library": task["library"],
                "class_name": task["class_name"],
                "game": task["game"],
                "resource_class": task["resource_class"],
                "status": "UNAVAILABLE",
                "reason": "synthetic test",
            }
            for task in tasks
        ]
    with (root / "RESULTS.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    write_json(
        root / "SUMMARY.json",
        {
            "source_head": "abc",
            "expected_model_game_pairs": 4,
            "observed_model_game_pairs": len(rows),
            "matrix_complete": len(rows) == 4,
            "holdout_evaluated": False,
            "prospective_evaluated": False,
            "promotion": False,
        },
    )
    write_json(root / "RESOURCE_PLAN.json", {"parallel_cpu_models": 2, "parallel_gpu_models": 1})
    write_json(root / "RESOURCE_SNAPSHOT.json", {"cpu_count": 16})
    write_json(root / "RESOURCE_LEASES.json", [])
    source_files = sorted(path for path in root.rglob("*") if path.is_file())
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{module.sha256_file(path)}  {path.relative_to(root).as_posix()}\n"
            for path in source_files
        ),
        encoding="utf-8",
    )
    return root


def test_preflight_accepts_exact_matrix(tmp_path: Path) -> None:
    module = load_module()
    root = build_campaign(tmp_path)
    result = module.validate_matrix_plan(
        module.read_json(root / "MATRIX_PLAN.json"),
        expected_models=2,
        expected_games=2,
        expected_pairs=4,
    )
    assert result["status"] == "PASS"
    assert result["observed_pairs"] == 4


def test_verify_accepts_complete_explicit_non_success_matrix(tmp_path: Path) -> None:
    module = load_module()
    root = build_campaign(tmp_path)
    summary, integrity = module.verify_campaign(
        root,
        expected_models=2,
        expected_games=2,
        expected_pairs=4,
    )
    assert summary["acceptance"] == "PASS"
    assert summary["gates"]["no_missing_task_keys"] is True
    assert summary["gates"]["all_successes_have_functional_evidence"] is True
    assert integrity["file_count"] > 0
    ok, failures = module.verify_existing_sha256s(root)
    assert ok is True
    assert failures == []


def test_verify_blocks_missing_pair(tmp_path: Path) -> None:
    module = load_module()
    rows = [
        {
            "ordinal": 1,
            "task_key": "m1::g1",
            "model_id": "m1",
            "library": "lib1",
            "class_name": "M1",
            "game": "g1",
            "resource_class": "CPU",
            "status": "UNAVAILABLE",
        },
        {
            "ordinal": 2,
            "task_key": "m1::g2",
            "model_id": "m1",
            "library": "lib1",
            "class_name": "M1",
            "game": "g2",
            "resource_class": "CPU",
            "status": "UNAVAILABLE",
        },
        {
            "ordinal": 3,
            "task_key": "m2::g1",
            "model_id": "m2",
            "library": "lib2",
            "class_name": "M2",
            "game": "g1",
            "resource_class": "GPU",
            "status": "UNAVAILABLE",
        },
    ]
    root = build_campaign(tmp_path, rows=rows)
    summary, _ = module.verify_campaign(
        root,
        expected_models=2,
        expected_games=2,
        expected_pairs=4,
    )
    assert summary["acceptance"] == "BLOCKED"
    assert summary["blockers"]["missing_task_keys"] == ["m2::g2"]


def test_verify_blocks_success_without_functional_evidence(tmp_path: Path) -> None:
    module = load_module()
    root = build_campaign(tmp_path)
    rows = module.read_jsonl(root / "RESULTS.jsonl")
    rows[0]["status"] = "PASS"
    with (root / "RESULTS.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    source_files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{module.sha256_file(path)}  {path.relative_to(root).as_posix()}\n"
            for path in source_files
        ),
        encoding="utf-8",
    )
    summary, _ = module.verify_campaign(
        root,
        expected_models=2,
        expected_games=2,
        expected_pairs=4,
    )
    assert summary["acceptance"] == "BLOCKED"
    assert summary["blockers"]["success_without_functional_evidence_task_keys"] == ["m1::g1"]


def test_kubuntu_launcher_is_bash_only_and_syntax_valid() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "powershell" not in text.lower()
    assert ".cmd" not in text.lower()
    assert "awk '" not in text
    assert "1044" in text
    assert "--resume" in text
    assert "HOLDOUT=CLOSED" in text
    result = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
