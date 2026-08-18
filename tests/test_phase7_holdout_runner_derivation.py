from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "phase7_holdout_runner" / "derive_canonical_runner.py"
SPEC = importlib.util.spec_from_file_location("phase7_derive_runner", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324


def fixture_runner() -> str:
    return """from __future__ import annotations

import json
from pathlib import Path
from typing import Any

class pd:
    class DataFrame:
        pass

def sha256_json(value):
    return "legacy"

def atomic_json(path, value):
    pass

def replay_component(
    *,
    seed: int,
    development: pd.DataFrame,
    expected_semantic_hash: str,
    frozen_trials_path: Path,
    replay_dir: Path,
) -> dict[str, Any]:
    best_config = {}
    replay_trials = []
    study = type(
        "S",
        (),
        {"best_trial": type("B", (), {"number": 14})(), "best_value": 1.0},
    )()
    serializable = json.loads(
        json.dumps(
            best_config,
            default=str,
        )
    )

    semantic_hash = sha256_json(
        serializable
    )

    if semantic_hash != expected_semantic_hash:

        raise RuntimeError(
            "best config semantic hash mismatch "
            f"for seed={seed}. "
            f"expected={expected_semantic_hash} "
            f"actual={semantic_hash}"
        )

    atomic_json(
        replay_dir / "x.json",
        {
            "semantic_config_sha256":
                semantic_hash,
        },
    )
    return best_config

def main():
    parser = None
    args = parser.parse_args()
    frozen_trials = Path("trials")
    frozen_config = Path("config")
    replay_dir = Path("replay")
    development = pd.DataFrame()
    component = {"semantic_config_sha256": "legacy"}
    seed = 1
    best_config = replay_component(
            seed=seed,
            development=
                development,
            expected_semantic_hash=
                str(
                    component[
                        "semantic_config_sha256"
                    ]
                ),
            frozen_trials_path=
                frozen_trials,
            replay_dir=
                replay_dir,
        )

    # ========================================================
    # B. Sequential Holdout
    # ========================================================
    return best_config
"""


def semantic_source() -> str:
    return """SEMANTIC_CONFIG_SCHEMA_V1 = "loto.semantic-config/v1"

def canonical_semantic_sha256_v1(config, *, legacy_object_states=None):
    return "same"
"""


def test_patch_preserves_legacy_evidence_and_adds_canonical_gate() -> None:
    patched = MOD.patch_runner_source(fixture_runner())
    assert "legacy_semantic_sha256_expected" in patched
    assert "canonical_semantic_sha256_frozen" in patched
    assert "canonical_semantic_sha256_replay" in patched
    assert "if semantic_hash != expected_semantic_hash" not in patched
    assert "canonical_frozen_hash != canonical_replay_hash" in patched
    assert "frozen_config_path: Path" in patched
    assert "frozen_config_path=" in patched
    compile(patched, "derived.py", "exec")


def test_patch_adds_replay_only_stop_before_holdout() -> None:
    patched = MOD.patch_runner_source(fixture_runner())
    assert '"--stop-after-replay"' in patched
    assert '"REPLAY_ONLY_VERIFICATION.json"' in patched
    assert '"REPLAY_VERIFIED_CANONICAL_V1"' in patched
    assert 'print("HOLDOUT_DRAWS_ACCESSED=0")' in patched
    assert 'print("ACTUALS_ACCESSED=0")' in patched
    assert 'print("HOLDOUT_EXECUTED=NO")' in patched
    assert patched.index("if args.stop_after_replay:") < patched.index("# B. Sequential Holdout")


def test_patch_accepts_crlf_source_and_normalizes_only_derived_text() -> None:
    crlf_source = fixture_runner().replace("\n", "\r\n")
    patched = MOD.patch_runner_source(crlf_source)

    assert "\r" not in patched
    assert "canonical_semantic_sha256_frozen" in patched
    assert '"--stop-after-replay"' in patched
    compile(patched, "derived.py", "exec")


def test_patch_fails_closed_when_anchor_missing() -> None:
    with pytest.raises(MOD.DerivationError, match="replay signature anchor count"):
        MOD.patch_runner_source("from __future__ import annotations\n")


def test_derive_rejects_wrong_runner_sha(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    semantic = tmp_path / "semantic.py"
    runner.write_bytes(fixture_runner().replace("\n", "\r\n").encode("utf-8"))
    semantic.write_text(semantic_source(), encoding="utf-8")
    with pytest.raises(MOD.DerivationError, match="original runner SHA mismatch"):
        MOD.derive_runner(
            runner=runner,
            semantic_config_source=semantic,
            output_dir=tmp_path / "out",
            expected_runner_sha256="0" * 64,
            expected_semantic_git_blob=git_blob(semantic.read_bytes()),
        )


def test_derive_rejects_wrong_semantic_blob(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    semantic = tmp_path / "semantic.py"
    runner.write_bytes(fixture_runner().replace("\n", "\r\n").encode("utf-8"))
    semantic.write_text(semantic_source(), encoding="utf-8")
    runner_sha = hashlib.sha256(runner.read_bytes()).hexdigest()
    with pytest.raises(MOD.DerivationError, match="Git blob mismatch"):
        MOD.derive_runner(
            runner=runner,
            semantic_config_source=semantic,
            output_dir=tmp_path / "out",
            expected_runner_sha256=runner_sha,
            expected_semantic_git_blob="0" * 40,
        )


def test_derive_writes_compilable_bundle_without_mutating_original(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    semantic = tmp_path / "semantic.py"
    runner.write_bytes(fixture_runner().replace("\n", "\r\n").encode("utf-8"))
    semantic.write_text(semantic_source(), encoding="utf-8")
    original = runner.read_bytes()
    runner_sha = hashlib.sha256(original).hexdigest()
    semantic_blob = git_blob(semantic.read_bytes())

    result = MOD.derive_runner(
        runner=runner,
        semantic_config_source=semantic,
        output_dir=tmp_path / "out",
        expected_runner_sha256=runner_sha,
        expected_semantic_git_blob=semantic_blob,
    )

    assert runner.read_bytes() == original
    assert result["original_runner_modified"] == "False"
    assert result["source_newline_normalization"] == "lf_for_in_memory_derivation_only"
    assert result["replay_only_mode_supported"] == "True"
    assert result["replay_only_holdout_access"] == "False"
    assert result["replay_only_actual_access"] == "False"
    assert (tmp_path / "out" / MOD.DERIVED_RUNNER_NAME).is_file()
    assert (tmp_path / "out" / MOD.SEMANTIC_MODULE_NAME).is_file()
    assert (tmp_path / "out" / MOD.MANIFEST_NAME).is_file()


def test_output_directory_must_be_new(tmp_path: Path) -> None:
    runner = tmp_path / "runner.py"
    semantic = tmp_path / "semantic.py"
    out = tmp_path / "out"
    runner.write_bytes(fixture_runner().replace("\n", "\r\n").encode("utf-8"))
    semantic.write_text(semantic_source(), encoding="utf-8")
    out.mkdir()
    with pytest.raises(MOD.DerivationError, match="already exists"):
        MOD.derive_runner(
            runner=runner,
            semantic_config_source=semantic,
            output_dir=out,
            expected_runner_sha256=hashlib.sha256(runner.read_bytes()).hexdigest(),
            expected_semantic_git_blob=git_blob(semantic.read_bytes()),
        )
