from __future__ import annotations

import argparse
import hashlib
import json
import py_compile
from pathlib import Path
from typing import Final

EXPECTED_ORIGINAL_RUNNER_SHA256: Final = (
    "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
)
EXPECTED_SEMANTIC_CONFIG_GIT_BLOB: Final = "257d4d4a88e56f6070200a67fd86b2beca73a3c1"
EXPECTED_MLFORECAST_VERSION: Final = "1.1.0"
PATCH_SCHEMA: Final = "phase7-holdout-canonical-runner-derivation/v1"
DERIVED_RUNNER_NAME: Final = "phase7_holdout_canonical_v1.py"
SEMANTIC_MODULE_NAME: Final = "phase7_semantic_config_v1.py"
MANIFEST_NAME: Final = "DERIVED_RUNNER_MANIFEST.json"


class DerivationError(RuntimeError):
    """Raised when exact Phase 7 runner derivation cannot be proven safe."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha1(value: bytes) -> str:
    header = f"blob {len(value)}\0".encode("ascii")
    return hashlib.sha1(header + value).hexdigest()  # noqa: S324 - Git object identity


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise DerivationError(f"{label} anchor count={count}; expected exactly 1")
    return text.replace(old, new, 1)


def _normalize_source_newlines(source: str) -> str:
    """Normalize only the in-memory derivation copy to deterministic LF newlines."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def patch_runner_source(source: str) -> str:
    source = _normalize_source_newlines(source)

    import_anchor = "from __future__ import annotations\n"
    import_replacement = (
        import_anchor
        + "\nfrom phase7_semantic_config_v1 import (\n"
        + "    SEMANTIC_CONFIG_SCHEMA_V1,\n"
        + "    canonical_semantic_sha256_v1,\n"
        + ")\n"
    )
    source = _replace_once(source, import_anchor, import_replacement, label="future import")

    signature_old = """def replay_component(
    *,
    seed: int,
    development: pd.DataFrame,
    expected_semantic_hash: str,
    frozen_trials_path: Path,
    replay_dir: Path,
) -> dict[str, Any]:"""
    signature_new = """def replay_component(
    *,
    seed: int,
    development: pd.DataFrame,
    expected_semantic_hash: str,
    frozen_trials_path: Path,
    frozen_config_path: Path,
    replay_dir: Path,
) -> dict[str, Any]:"""
    source = _replace_once(source, signature_old, signature_new, label="replay signature")

    legacy_gate_old = """    serializable = json.loads(
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
"""
    canonical_gate_new = f'''    serializable = json.loads(
        json.dumps(
            best_config,
            default=str,
        )
    )

    # Preserve the historical process-dependent hash as audit evidence.
    # It is deliberately NOT used as the semantic equality gate.
    semantic_hash = sha256_json(
        serializable
    )
    legacy_semantic_hash_match = (
        semantic_hash
        == expected_semantic_hash
    )

    from importlib.metadata import version as distribution_version

    mlforecast_version = distribution_version(
        "mlforecast"
    )
    if mlforecast_version != "{EXPECTED_MLFORECAST_VERSION}":
        raise RuntimeError(
            "MLForecast version drift before Holdout: "
            f"{{mlforecast_version}}"
        )

    frozen_payload = json.loads(
        frozen_config_path.read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(frozen_payload, dict) or "config" not in frozen_payload:
        raise RuntimeError(
            f"frozen config payload missing config: seed={{seed}}"
        )

    legacy_object_states = {{
        "mlforecast.target_transforms.Differences": {{
            "differences": [1],
        }},
        "mlforecast.target_transforms.GlobalSklearnTransformer": {{
            "transformer": {{
                "class": "sklearn.preprocessing.FunctionTransformer",
                "func": "numpy.log1p",
                "inverse_func": "numpy.expm1",
                "validate": False,
                "accept_sparse": False,
                "check_inverse": True,
                "feature_names_out": None,
                "kw_args": None,
                "inv_kw_args": None,
            }},
        }},
    }}

    canonical_frozen_hash = (
        canonical_semantic_sha256_v1(
            frozen_payload["config"],
            legacy_object_states=
                legacy_object_states,
        )
    )
    canonical_replay_hash = (
        canonical_semantic_sha256_v1(
            best_config,
            legacy_object_states=
                legacy_object_states,
        )
    )

    if canonical_frozen_hash != canonical_replay_hash:
        raise RuntimeError(
            "canonical semantic hash mismatch "
            f"for seed={{seed}}. "
            f"frozen={{canonical_frozen_hash}} "
            f"replay={{canonical_replay_hash}}"
        )
'''
    source = _replace_once(
        source,
        legacy_gate_old,
        canonical_gate_new,
        label="legacy semantic gate",
    )

    artifact_old = """            "semantic_config_sha256":
                semantic_hash,"""
    artifact_new = """            "semantic_config_sha256":
                semantic_hash,
            "legacy_semantic_sha256_expected":
                expected_semantic_hash,
            "legacy_semantic_sha256_replay":
                semantic_hash,
            "legacy_semantic_hash_match":
                legacy_semantic_hash_match,
            "canonical_semantic_schema":
                SEMANTIC_CONFIG_SCHEMA_V1,
            "canonical_semantic_sha256_frozen":
                canonical_frozen_hash,
            "canonical_semantic_sha256_replay":
                canonical_replay_hash,
            "canonical_semantic_match":
                True,
            "mlforecast_version":
                mlforecast_version,"""
    source = _replace_once(source, artifact_old, artifact_new, label="replay artifact fields")

    call_old = """            frozen_trials_path=
                frozen_trials,
            replay_dir=
                replay_dir,"""
    call_new = """            frozen_trials_path=
                frozen_trials,
            frozen_config_path=
                frozen_config,
            replay_dir=
                replay_dir,"""
    source = _replace_once(source, call_old, call_new, label="replay call")

    parse_args_old = """    args = parser.parse_args()
"""
    parse_args_new = """    parser.add_argument(
        "--stop-after-replay",
        action="store_true",
        help=(
            "Verify the frozen 4-seed/80-trial replay and canonical semantic gate, "
            "then exit before Holdout prediction or actual access."
        ),
    )

    args = parser.parse_args()
"""
    source = _replace_once(source, parse_args_old, parse_args_new, label="parse args")

    holdout_marker = """    # ========================================================
    # B. Sequential Holdout
    # ========================================================"""
    replay_only_gate = """    if args.stop_after_replay:
        progress["status"] = "PASS"
        progress["phase"] = "REPLAY_VERIFIED_CANONICAL_V1"
        progress["current_seed"] = None
        progress["current_draw"] = None

        atomic_json(
            progress_path,
            progress,
        )
        atomic_json(
            root / "REPLAY_ONLY_VERIFICATION.json",
            {
                "schema_version":
                    "phase7-replay-only-verification/v1",
                "status":
                    "PASS",
                "components_verified":
                    4,
                "verification_trial_count":
                    80,
                "canonical_semantic_schema":
                    SEMANTIC_CONFIG_SCHEMA_V1,
                "freeze_sha256":
                    args.freeze_sha256,
                "holdout_draws_accessed":
                    0,
                "actuals_accessed":
                    0,
                "holdout_executed":
                    False,
                "verified_at_utc":
                    now(),
            },
        )

        print("PHASE 7 REPLAY VERIFICATION COMPLETE")
        print("HOLDOUT_DRAWS_ACCESSED=0")
        print("ACTUALS_ACCESSED=0")
        print("HOLDOUT_EXECUTED=NO")
        return 0

"""
    source = _replace_once(
        source,
        holdout_marker,
        replay_only_gate + holdout_marker,
        label="sequential Holdout marker",
    )

    return source


def derive_runner(
    *,
    runner: Path,
    semantic_config_source: Path,
    output_dir: Path,
    expected_runner_sha256: str = EXPECTED_ORIGINAL_RUNNER_SHA256,
    expected_semantic_git_blob: str = EXPECTED_SEMANTIC_CONFIG_GIT_BLOB,
) -> dict[str, str]:
    if not runner.is_file():
        raise DerivationError(f"runner missing: {runner}")
    if not semantic_config_source.is_file():
        raise DerivationError(f"semantic config source missing: {semantic_config_source}")
    if output_dir.exists():
        raise DerivationError(f"output directory already exists: {output_dir}")

    original_bytes = runner.read_bytes()
    original_sha = sha256_bytes(original_bytes)
    if original_sha != expected_runner_sha256:
        raise DerivationError(
            f"original runner SHA mismatch: expected={expected_runner_sha256} actual={original_sha}"
        )

    semantic_bytes = semantic_config_source.read_bytes()
    semantic_blob = git_blob_sha1(semantic_bytes)
    if semantic_blob != expected_semantic_git_blob:
        raise DerivationError(
            "semantic_config.py Git blob mismatch: "
            f"expected={expected_semantic_git_blob} actual={semantic_blob}"
        )

    try:
        source = original_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DerivationError("runner is not UTF-8") from exc

    derived_source = patch_runner_source(source)

    output_dir.mkdir(parents=True, exist_ok=False)
    derived_runner = output_dir / DERIVED_RUNNER_NAME
    semantic_copy = output_dir / SEMANTIC_MODULE_NAME
    manifest = output_dir / MANIFEST_NAME

    derived_runner.write_text(derived_source, encoding="utf-8", newline="\n")
    semantic_copy.write_bytes(semantic_bytes)

    try:
        py_compile.compile(str(derived_runner), doraise=True)
        py_compile.compile(str(semantic_copy), doraise=True)
    except py_compile.PyCompileError as exc:
        raise DerivationError(f"derived source compile failed: {exc}") from exc

    if runner.read_bytes() != original_bytes:
        raise DerivationError("original runner changed during derivation")
    if semantic_config_source.read_bytes() != semantic_bytes:
        raise DerivationError("semantic config source changed during derivation")

    derived_sha = sha256_bytes(derived_runner.read_bytes())
    semantic_sha = sha256_bytes(semantic_copy.read_bytes())

    payload = {
        "schema_version": PATCH_SCHEMA,
        "original_runner_path": str(runner),
        "original_runner_sha256": original_sha,
        "derived_runner_file": derived_runner.name,
        "derived_runner_sha256": derived_sha,
        "semantic_module_file": semantic_copy.name,
        "semantic_module_sha256": semantic_sha,
        "semantic_module_git_blob": semantic_blob,
        "semantic_schema": "loto.semantic-config/v1",
        "mlforecast_version_required": EXPECTED_MLFORECAST_VERSION,
        "legacy_semantic_hash_preserved": True,
        "legacy_semantic_hash_is_gate": False,
        "canonical_semantic_hash_is_gate": True,
        "legacy_differences_state": [1],
        "legacy_global_sklearn_transformer": "numpy.log1p/numpy.expm1",
        "legacy_lag_transform_bridge": (
            "mlf_init_params.lag_transforms positive int/JSON-string keys + "
            "ExponentiallyWeightedMean(alpha=0.9)"
        ),
        "source_newline_normalization": "lf_for_in_memory_derivation_only",
        "replay_only_mode_supported": True,
        "replay_only_holdout_access": False,
        "replay_only_actual_access": False,
        "original_runner_modified": False,
    }
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {key: str(value) for key, value in payload.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--semantic-config-source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    result = derive_runner(
        runner=args.runner,
        semantic_config_source=semantic_config_source if False else args.semantic_config_source,
        output_dir=args.output_dir,
    )
    for key in sorted(result):
        print(f"{key.upper()}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
