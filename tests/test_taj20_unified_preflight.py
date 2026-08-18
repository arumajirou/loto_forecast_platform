from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "runtime_audit" / "taj20_preflight.py"
LAUNCHER = ROOT / "tools" / "taj20.sh"
GAMES = ["mini", "numbers3", "numbers4", "bingo5", "loto6", "loto7"]


def load_module():
    spec = importlib.util.spec_from_file_location("taj20_preflight", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def build_identity_plan(tmp_path: Path) -> Path:
    root = tmp_path / "identity"
    root.mkdir()
    broad = [
        {"model_id": f"broad-{index:03d}", "catalog_source": "existing"}
        for index in range(174)
    ]
    probabilistic = [
        {
            "model_id": f"pp-{index:03d}",
            "catalog_source": "probabilistic",
            "primary_backend": "builtin",
        }
        for index in range(76)
    ]
    native = [
        {
            "model_id": f"pp-{index:03d}",
            "primary_backend": "builtin",
            "primary_profile": None,
            "implementation_kind": "analytic",
            "module": "example",
            "graph_id": f"graph-{index}",
            "runtime_tier": "standard",
        }
        for index in range(76)
    ]
    write_json(
        root / "IDENTITY_SUMMARY.json",
        {
            "broad_catalog_identities": 174,
            "probabilistic_catalog_identities": 76,
            "unified_catalog_identities": 250,
            "probabilistic_native_identities": 76,
            "canonical_games": GAMES,
            "unified_model_game_cross_product": 1500,
        },
    )
    write_json(root / "UNIFIED_CATALOG.json", [*broad, *probabilistic])
    write_json(root / "PROBABILISTIC_NATIVE.json", native)
    return root


def build_taj19_campaign(tmp_path: Path, module) -> Path:
    root = tmp_path / "taj19"
    root.mkdir()
    write_json(root / "payload.json", {"evidence": "immutable"})
    write_json(
        root / "CAMPAIGN_SUMMARY.json",
        {
            "acceptance": "PASS",
            "source_head": "source-head",
            "identity": {"observed_pairs": 1044},
            "gates": {"matrix": True, "evidence": True},
        },
    )
    write_json(root / "ARTIFACT_MANIFEST.json", {"schema_version": "test"})
    paths = sorted(path for path in root.iterdir() if path.is_file())
    (root / "SHA256SUMS").write_text(
        "".join(f"{module.sha256_file(path)}  {path.name}\n" for path in paths),
        encoding="utf-8",
    )
    return root


def test_preflight_builds_exact_456_incremental_tasks_and_reuses_1044(tmp_path, monkeypatch) -> None:
    module = load_module()
    identity = build_identity_plan(tmp_path)
    campaign = build_taj19_campaign(tmp_path, module)
    monkeypatch.setattr(module, "EXPECTED_TAJ19_MANIFEST_SHA", module.sha256_file(campaign / "ARTIFACT_MANIFEST.json"))
    monkeypatch.setattr(module, "EXPECTED_TAJ19_SHA256SUMS_SHA", module.sha256_file(campaign / "SHA256SUMS"))
    output = tmp_path / "preflight"
    result = module.write_preflight(output, identity, campaign)
    assert result["status"] == "PASS"
    assert result["identity_contract"]["reused_pairs"] == 1044
    assert result["identity_contract"]["incremental_pairs"] == 456
    assert result["identity_contract"]["final_pairs"] == 1500
    tasks = json.loads((output / "INCREMENTAL_MATRIX_PLAN.json").read_text())["tasks"]
    assert len(tasks) == 456
    assert len({row["task_key"] for row in tasks}) == 456
    assert (output / "REUSE_PROVENANCE.json").is_file()
    assert (output / "SHA256SUMS").is_file()


def test_identity_count_drift_is_fail_closed(tmp_path) -> None:
    module = load_module()
    identity = build_identity_plan(tmp_path)
    summary_path = identity / "IDENTITY_SUMMARY.json"
    summary = json.loads(summary_path.read_text())
    summary["probabilistic_catalog_identities"] = 75
    write_json(summary_path, summary)
    try:
        module.verify_identity_plan(identity)
    except module.PreflightError as exc:
        assert "inventory drift" in str(exc)
    else:
        raise AssertionError("TAJ-20 must block identity-count drift")


def test_taj19_hash_drift_is_fail_closed(tmp_path, monkeypatch) -> None:
    module = load_module()
    campaign = build_taj19_campaign(tmp_path, module)
    monkeypatch.setattr(module, "EXPECTED_TAJ19_MANIFEST_SHA", "0" * 64)
    monkeypatch.setattr(module, "EXPECTED_TAJ19_SHA256SUMS_SHA", module.sha256_file(campaign / "SHA256SUMS"))
    try:
        module.verify_taj19(campaign)
    except module.PreflightError as exc:
        assert "ARTIFACT_MANIFEST identity mismatch" in str(exc)
    else:
        raise AssertionError("TAJ-20 must block TAJ-19 evidence hash drift")


def test_kubuntu_launcher_is_bash_only_and_plan_only() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "powershell" not in text.lower()
    assert ".cmd" not in text.lower()
    assert "TAJ20_TAJ19_CAMPAIGN" in text
    assert "plan_all_execution_identities.py" in text
    assert "1044" in text
    assert "456" in text
    assert "1500" in text
    assert "holdout" in text.lower()
    result = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
