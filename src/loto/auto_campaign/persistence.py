from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from loto.auto_campaign.p1_compat import (
    save_neuralforecast_compat,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=repr) + "\n",
        encoding="utf-8",
    )


def write_sha256s(root: Path) -> Path:
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in files]
    target = root / "SHA256SUMS"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def verify_sha256s(root: Path, *, require_complete_listing: bool = True) -> list[str]:
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        return ["SHA256SUMS missing"]
    failures: list[str] = []
    listed: set[str] = set()
    for line_number, line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"malformed-line:{line_number}")
            continue
        listed.add(relative)
        path = root / relative
        if not path.is_file():
            failures.append(f"missing:{relative}")
        elif sha256_file(path) != expected:
            failures.append(f"mismatch:{relative}")
    if require_complete_listing:
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        }
        for relative in sorted(actual - listed):
            failures.append(f"unlisted:{relative}")
        for relative in sorted(listed - actual):
            failures.append(f"listed-but-missing:{relative}")
    return failures


@contextmanager
def atomic_directory(target: Path, *, enabled: bool = True) -> Iterator[Path]:
    target = target.resolve()
    partial = target.with_name(target.name + ".partial")
    if target.exists():
        raise FileExistsError(target)
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True, exist_ok=False)
    try:
        yield partial
        if enabled:
            os.replace(partial, target)
        else:
            partial.rename(target)
    except Exception:
        raise


def finite_state_dict(model: Any) -> bool:
    try:
        state = model.state_dict()
    except AttributeError:
        return False
    for value in state.values():
        array = value.detach().cpu().numpy()
        if not np.isfinite(array).all():
            return False
    return True


def save_best_model_bundle(
    *,
    nf: Any,
    auto_model: Any,
    target: Path,
    train_panel: pd.DataFrame,
    prediction_before: pd.DataFrame,
    requested_config: dict[str, Any],
    effective_config: dict[str, Any],
    base_auto_args: dict[str, Any],
    neuralforecast_args: dict[str, Any],
    fit_args: dict[str, Any],
    runtime: dict[str, Any],
    gpu_pid: dict[str, Any],
    save_dataset: bool,
    atomic: bool,
) -> dict[str, Any]:
    with atomic_directory(target, enabled=atomic) as work:
        write_json(work / "requested_config.json", requested_config)
        write_json(work / "effective_config.json", effective_config)
        write_json(work / "base_auto_args.json", base_auto_args)
        write_json(work / "neuralforecast_args.json", neuralforecast_args)
        write_json(work / "fit_args.json", fit_args)
        write_json(work / "runtime.json", runtime)
        write_json(work / "gpu_pid.json", gpu_pid)
        train_panel.to_parquet(work / "train_panel.parquet", index=False)
        prediction_before.to_parquet(work / "prediction_before_save.parquet", index=False)

        neuralforecast_dir = work / "neuralforecast"
        save_neuralforecast_compat(
            nf,
            path=str(neuralforecast_dir),
            save_dataset=save_dataset,
            overwrite=True,
        )
        inner = getattr(auto_model, "model", None)
        if inner is None:
            raise RuntimeError("AutoModel has no fitted .model")
        import torch

        state = {name: value.detach().cpu() for name, value in inner.state_dict().items()}
        torch.save(state, work / "state_dict.pt")
        state_finite = finite_state_dict(inner)
        if not state_finite:
            raise RuntimeError("non-finite state_dict")
        statistics: list[dict[str, Any]] = []
        for name, value in state.items():
            array = value.numpy()
            statistics.append(
                {
                    "name": name,
                    "shape": list(array.shape),
                    "dtype": str(array.dtype),
                    "numel": int(array.size),
                    "finite": bool(np.isfinite(array).all()),
                    "mean": float(array.mean()) if array.size else None,
                    "std": float(array.std()) if array.size else None,
                    "min": float(array.min()) if array.size else None,
                    "max": float(array.max()) if array.size else None,
                }
            )
        pd.DataFrame(statistics).to_parquet(
            work / "parameter_statistics.parquet",
            index=False,
        )
        (work / "model_structure.txt").write_text(
            repr(inner) + "\n",
            encoding="utf-8",
        )
        write_json(
            work / "train_contract.json",
            {
                "train_rows": len(train_panel),
                "unique_ids": sorted(train_panel["unique_id"].astype(str).unique().tolist()),
                "first_ds": int(train_panel["ds"].min()),
                "last_ds": int(train_panel["ds"].max()),
            },
        )
        write_json(
            work / "manifest.json",
            {
                "status": "PASS",
                "state_dict_finite": state_finite,
                "train_rows": len(train_panel),
                "prediction_rows": len(prediction_before),
                "state_dict_sha256": sha256_file(work / "state_dict.pt"),
                "train_panel_sha256": sha256_file(work / "train_panel.parquet"),
                "prediction_before_sha256": sha256_file(work / "prediction_before_save.parquet"),
            },
        )
        write_sha256s(work)
    return json.loads((target / "manifest.json").read_text(encoding="utf-8"))
