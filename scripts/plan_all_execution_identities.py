#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from loto.game.geometry import known_games
from loto.models.catalog_full import build_catalog
from loto.probabilistic.catalog import (
    build_unified_catalog_rows,
    list_probabilistic_model_specs,
)
from loto.probabilistic.native_registry import list_native_implementations

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory canonical model identities and execution surfaces without "
            "conflating them with runtime-success counts."
        )
    )
    parser.add_argument("--output", required=True)
    return parser


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provider_scripts() -> list[str]:
    return sorted(path.name for path in (ROOT / "scripts").glob("run_*_provider.py"))


def _nf_local_extension_dirs() -> list[str]:
    base = ROOT / "src" / "loto" / "neuralforecast"
    candidates = ("auto_frets", "auto_scinet", "auto_segrnn", "auto_timellm")
    return [name for name in candidates if (base / name).is_dir()]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"refusing to reuse identity-plan output: {output}")
    output.mkdir(parents=True)

    broad = build_catalog()
    probabilistic = list_probabilistic_model_specs()
    unified = build_unified_catalog_rows()
    native = list_native_implementations()
    games = list(known_games())

    broad_ids = [entry.model_id for entry in broad]
    probabilistic_ids = [spec.model_id for spec in probabilistic]
    unified_ids = [str(row["model_id"]) for row in unified]
    native_ids = [item.model_id for item in native]

    if len(set(broad_ids)) != len(broad_ids):
        raise RuntimeError("broad catalog contains duplicate model IDs")
    if len(set(probabilistic_ids)) != len(probabilistic_ids):
        raise RuntimeError("probabilistic catalog contains duplicate model IDs")
    if len(set(unified_ids)) != len(unified_ids):
        raise RuntimeError("unified catalog contains duplicate model IDs")
    if set(native_ids) != set(probabilistic_ids):
        missing_native = sorted(set(probabilistic_ids) - set(native_ids))
        extra_native = sorted(set(native_ids) - set(probabilistic_ids))
        raise RuntimeError(
            "probabilistic/native identity mismatch: "
            f"missing_native={missing_native}; extra_native={extra_native}"
        )

    providers = _provider_scripts()
    nf_extensions = _nf_local_extension_dirs()
    broad_game_pairs = len(broad_ids) * len(games)
    unified_game_pairs = len(unified_ids) * len(games)

    summary = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "identity_semantics": (
            "A model identity is distinct from an execution surface and from a model-game, "
            "seed, fold, trial, backend, revision, or parameter execution unit."
        ),
        "broad_catalog_identities": len(broad_ids),
        "probabilistic_catalog_identities": len(probabilistic_ids),
        "unified_catalog_identities": len(unified_ids),
        "probabilistic_native_identities": len(native_ids),
        "canonical_games": games,
        "broad_model_game_cross_product": broad_game_pairs,
        "unified_model_game_cross_product": unified_game_pairs,
        "provider_script_count": len(providers),
        "provider_scripts": providers,
        "neuralforecast_local_extension_count": len(nf_extensions),
        "neuralforecast_local_extensions": nf_extensions,
        "important_boundary": (
            "The model-game cross products are planning upper bounds. Unsupported and "
            "non-routable pairs must remain explicit statuses rather than being counted as "
            "successful runtime combinations. Provider scripts and local extensions are "
            "execution surfaces and are not added to the unified identity count without "
            "canonical de-duplication."
        ),
    }
    _atomic_json(output / "IDENTITY_SUMMARY.json", summary)
    _atomic_json(output / "UNIFIED_CATALOG.json", unified)
    _atomic_json(
        output / "PROBABILISTIC_NATIVE.json",
        [item.to_dict() for item in native],
    )
    _atomic_json(
        output / "EXECUTION_SURFACES.json",
        {
            "provider_scripts": providers,
            "neuralforecast_local_extensions": nf_extensions,
        },
    )

    checksum_lines = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(f"{_sha256(path)}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
