from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_kronos_base_provider.py"


def _load_provider() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_kronos_base_provider", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_explicit_model_snapshot_override_wins(tmp_path: Path) -> None:
    provider = _load_provider()
    override = tmp_path / provider.MODEL_REVISION
    env = {
        provider.MODEL_SNAPSHOT_ENV: str(override),
        "HF_HUB_CACHE": str(tmp_path / "ignored-hub"),
    }

    resolved = provider.resolve_snapshot_path(
        provider.MODEL_REPO_ID,
        provider.MODEL_REVISION,
        override_env=provider.MODEL_SNAPSHOT_ENV,
        env=env,
        home=tmp_path / "ignored-home",
    )

    assert resolved == override


def test_hf_hub_cache_is_used_for_model_snapshot(tmp_path: Path) -> None:
    provider = _load_provider()
    hub = tmp_path / "custom-hub"

    resolved = provider.resolve_snapshot_path(
        provider.MODEL_REPO_ID,
        provider.MODEL_REVISION,
        override_env=provider.MODEL_SNAPSHOT_ENV,
        env={"HF_HUB_CACHE": str(hub)},
        home=tmp_path / "ignored-home",
    )

    assert resolved == (
        hub / "models--NeoQuasar--Kronos-base" / "snapshots" / provider.MODEL_REVISION
    )


def test_hf_home_is_used_for_tokenizer_snapshot(tmp_path: Path) -> None:
    provider = _load_provider()
    hf_home = tmp_path / "huggingface"

    resolved = provider.resolve_snapshot_path(
        provider.TOKENIZER_REPO_ID,
        provider.TOKENIZER_REVISION,
        override_env=provider.TOKENIZER_SNAPSHOT_ENV,
        env={"HF_HOME": str(hf_home)},
        home=tmp_path / "ignored-home",
    )

    assert resolved == (
        hf_home
        / "hub"
        / "models--NeoQuasar--Kronos-Tokenizer-base"
        / "snapshots"
        / provider.TOKENIZER_REVISION
    )


def test_xdg_cache_home_matches_hugging_face_default_shape(tmp_path: Path) -> None:
    provider = _load_provider()
    xdg_cache = tmp_path / "xdg-cache"

    resolved = provider.resolve_hf_hub_cache(
        env={"XDG_CACHE_HOME": str(xdg_cache)},
        home=tmp_path / "ignored-home",
    )

    assert resolved == xdg_cache / "huggingface" / "hub"


def test_default_cache_uses_supplied_home(tmp_path: Path) -> None:
    provider = _load_provider()

    resolved = provider.resolve_hf_hub_cache(env={}, home=tmp_path)

    assert resolved == tmp_path / ".cache" / "huggingface" / "hub"


def test_snapshot_resolution_has_no_machine_specific_default() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "/mnt/e/env/huggingface" not in text
    assert "C:\\" not in text
    assert "MODEL_SNAPSHOT = Path(" not in text
    assert "TOKENIZER_SNAPSHOT = Path(" not in text
