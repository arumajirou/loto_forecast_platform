from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools" / "phase7_holdout_runner"
MODULE_PATH = TOOLS / "pr355_replay_only_bootstrap.py"

sys.path.insert(0, str(TOOLS))
try:
    SPEC = importlib.util.spec_from_file_location("phase7_pr355_replay_bootstrap", MODULE_PATH)
    assert SPEC is not None and SPEC.loader is not None
    MOD = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MOD)
finally:
    sys.path.pop(0)


def test_replay_bootstrap_pins_only_critical_pr_files() -> None:
    assert MOD.PR_FILES == (
        "src/loto/evaluation/semantic_config.py",
        "tools/phase7_holdout_runner/derive_canonical_runner.py",
    )
    assert MOD.EXPECTED_PR_BLOBS[MOD.PR_FILES[0]] == (
        "257d4d4a88e56f6070200a67fd86b2beca73a3c1"
    )
    assert MOD.EXPECTED_PR_BLOBS[MOD.PR_FILES[1]] == (
        "efa988d671cb31820d4a4292498dd034c85ce481"
    )


def test_materialization_verifies_git_blob_without_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"print('safe')\n"
    expected_blob = MOD.git_blob_sha1(payload)
    monkeypatch.setattr(MOD, "PR_FILES", ("safe.py",))
    monkeypatch.setattr(MOD, "EXPECTED_PR_BLOBS", {"safe.py": expected_blob})
    monkeypatch.setattr(MOD, "git_show_bytes", lambda repo, head, path: payload)

    MOD.materialize_pr_files(tmp_path, "a" * 40, tmp_path / "out")

    assert (tmp_path / "out" / "safe.py").read_bytes() == payload


def test_materialization_fails_closed_on_blob_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(MOD, "PR_FILES", ("safe.py",))
    monkeypatch.setattr(MOD, "EXPECTED_PR_BLOBS", {"safe.py": "0" * 40})
    monkeypatch.setattr(
        MOD,
        "git_show_bytes",
        lambda repo, head, path: b"different\n",
    )

    with pytest.raises(MOD.ReplayBootstrapError, match="critical blob drift"):
        MOD.materialize_pr_files(tmp_path, "a" * 40, tmp_path / "out")
