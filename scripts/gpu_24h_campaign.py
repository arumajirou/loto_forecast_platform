#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import torch

    torch.set_float32_matmul_precision("high")
except ImportError:
    pass

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required in the project environment") from exc


NIXXTLA_MODELS = [
    "nf-dlinear", "nf-nlinear", "nf-nhits", "nf-nbeats", "nf-nbeatsx",
    "nf-tide", "nf-tcn", "nf-gru", "nf-lstm", "nf-deepar", "nf-tft",
    "nf-patchtst", "nf-timesnet", "nf-tsmixer", "nf-timemixer",
    "nf-itransformer", "nf-vanilla-transformer",
]

FOUNDATION_MODELS = [
    "chronos-bolt-tiny", "chronos-2-small", "timesfm-2.5",
    "granite-ttm", "tirex", "moirai",
]

COMMON_GRID = {
    "input_size": [32, 64, 128, 256],
    "max_steps": [300, 600, 1000, 2000],
    "learning_rate": [1e-4, 3e-4, 1e-3],
    "batch_size": [32, 64, 128],
}

MODEL_GRID: dict[str, dict[str, list[Any]]] = {
    "nf-dlinear": {
        "moving_avg_window": [5, 13, 25],
        "scaler_type": ["identity", "robust"],
    },
    "nf-nlinear": {
        "scaler_type": ["identity", "robust"],
    },
    "nf-nhits": {
        "n_blocks": [[1, 1, 1], [2, 2, 2]],
        "mlp_units": [[[256, 256], [256, 256], [256, 256]],
                      [[512, 512], [512, 512], [512, 512]]],
        "dropout_prob_theta": [0.0, 0.1, 0.2],
    },
    "nf-nbeats": {
        "stack_types": [["identity", "identity"], ["trend", "seasonality"]],
        "n_blocks": [[1, 1], [2, 2]],
        "mlp_units": [[[256, 256], [256, 256]], [[512, 512], [512, 512]]],
    },
    "nf-nbeatsx": {
        "n_blocks": [[1, 1, 1], [2, 2, 2]],
        "mlp_units": [[[256, 256], [256, 256], [256, 256]],
                      [[512, 512], [512, 512], [512, 512]]],
    },
    "nf-tide": {
        "hidden_size": [128, 256, 512],
        "decoder_output_dim": [16, 32, 64],
        "num_encoder_layers": [1, 2, 3],
        "num_decoder_layers": [1, 2, 3],
        "dropout": [0.0, 0.1, 0.2],
    },
    "nf-tcn": {
        "encoder_hidden_size": [128, 256, 512],
        "context_size": [5, 10, 20],
        "kernel_size": [2, 3, 5],
        "dilations": [[1, 2, 4, 8], [1, 2, 4, 8, 16]],
    },
    "nf-gru": {
        "encoder_hidden_size": [128, 256, 512],
        "encoder_n_layers": [1, 2, 3],
        "decoder_hidden_size": [128, 256],
        "decoder_layers": [1, 2],
        "dropout": [0.0, 0.1, 0.2],
    },
    "nf-lstm": {
        "encoder_hidden_size": [128, 256, 512],
        "encoder_n_layers": [1, 2, 3],
        "decoder_hidden_size": [128, 256],
        "decoder_layers": [1, 2],
        "dropout": [0.0, 0.1, 0.2],
    },
    "nf-deepar": {
        "lstm_hidden_size": [128, 256, 512],
        "lstm_n_layers": [1, 2, 3],
        "dropout_prob": [0.0, 0.1, 0.2],
        "num_samples": [100, 300],
    },
    "nf-tft": {
        "hidden_size": [64, 128, 256],
        "n_head": [2, 4, 8],
        "dropout": [0.05, 0.1, 0.2],
    },
    "nf-patchtst": {
        "hidden_size": [128, 256, 512],
        "n_heads": [4, 8],
        "encoder_layers": [2, 3, 4],
        "patch_len": [8, 16, 32],
        "stride": [4, 8, 16],
        "dropout": [0.05, 0.1, 0.2],
    },
    "nf-timesnet": {
        "hidden_size": [64, 128, 256],
        "conv_hidden_size": [64, 128, 256],
        "top_k": [3, 5, 8],
        "num_kernels": [4, 6, 8],
        "encoder_layers": [1, 2, 3],
    },
    "nf-tsmixer": {
        "n_block": [2, 4, 6],
        "ff_dim": [64, 128, 256],
        "dropout": [0.05, 0.1, 0.2],
    },
    "nf-timemixer": {
        "d_model": [64, 128, 256],
        "d_ff": [128, 256, 512],
        "e_layers": [1, 2, 3],
        "down_sampling_layers": [1, 2, 3],
    },
    "nf-itransformer": {
        "hidden_size": [128, 256, 512],
        "n_heads": [4, 8],
        "e_layers": [2, 3, 4],
        "d_ff": [256, 512, 1024],
        "dropout": [0.05, 0.1, 0.2],
    },
    "nf-vanilla-transformer": {
        "hidden_size": [128, 256, 512],
        "n_head": [4, 8],
        "encoder_layers": [2, 3, 4],
        "dropout": [0.05, 0.1, 0.2],
    },
}

FOUNDATION_GRID: dict[str, dict[str, list[Any]]] = {
    "chronos-bolt-tiny": {
        "num_samples": [20, 50, 100],
        "temperature": [0.7, 1.0],
    },
    "chronos-2-small": {
        "fine_tune": [False, True],
        "learning_rate": [1e-5, 3e-5, 1e-4],
        "max_steps": [100, 300, 600],
    },
    "timesfm-2.5": {
        "context_len": [128, 256, 512],
        "horizon_len": [1, 7, 14],
    },
    "granite-ttm": {
        "context_length": [128, 256, 512],
        "prediction_length": [1, 7, 14],
        "fine_tune": [False, True],
    },
    "tirex": {
        "num_samples": [50, 100, 300],
    },
    "moirai": {
        "context_length": [128, 256, 512],
        "num_samples": [50, 100, 300],
    },
}

MODEL_ARTIFACT_SUFFIXES = {
    ".ckpt", ".pt", ".pth", ".pkl", ".pickle", ".joblib", ".ubj", ".onnx",
    ".safetensors", ".bin"
}


@dataclass
class Trial:
    trial_id: str
    model_id: str
    params: dict[str, Any]
    phase: str
    status: str = "PENDING"
    elapsed_seconds: float = 0.0
    returncode: int | None = None
    error_class: str = ""
    config_path: str = ""
    run_dir: str = ""
    log_path: str = ""
    artifacts: list[str] | None = None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha12(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def read_catalog(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("model_catalog.json must be a JSON array")
    return payload


def supports_model(catalog: list[dict[str, Any]], model_id: str) -> bool:
    return any(row.get("model_id") == model_id for row in catalog)


def choose_models(args: argparse.Namespace, catalog: list[dict[str, Any]]) -> list[str]:
    if args.models:
        return sorted(set(args.models))
    models: list[str] = []
    if args.include_nixtla:
        models.extend(NIXXTLA_MODELS)
    if args.include_foundation:
        models.extend(FOUNDATION_MODELS)
    return [m for m in dict.fromkeys(models) if supports_model(catalog, m)]


def cartesian_sample(grid: dict[str, list[Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    keys = sorted(grid)
    combos = [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]
    rnd = random.Random(seed)
    rnd.shuffle(combos)
    return combos[:limit]


def build_trials(models: list[str], per_model: int, seed: int) -> list[Trial]:
    trials: list[Trial] = []
    for m_index, model in enumerate(models):
        if model.startswith("nf-"):
            grid = copy.deepcopy(COMMON_GRID)
            grid.update(MODEL_GRID.get(model, {}))
        else:
            grid = copy.deepcopy(FOUNDATION_GRID.get(model, {}))
        combos = cartesian_sample(grid, per_model, seed + m_index)
        for idx, params in enumerate(combos, 1):
            phase = "foundation" if model in FOUNDATION_MODELS else "nixtla"
            trial_id = f"{model}-{idx:04d}-{sha12(params)}"
            trials.append(Trial(trial_id=trial_id, model_id=model, params=params, phase=phase))
    random.Random(seed).shuffle(trials)
    return trials


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path: Path, trials: list[Trial]) -> None:
    rows = []
    for t in trials:
        row = asdict(t)
        row["params"] = json.dumps(t.params, sort_keys=True, ensure_ascii=False)
        row["artifacts"] = json.dumps(t.artifacts or [], ensure_ascii=False)
        rows.append(row)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def classify(text: str, returncode: int) -> str:
    low = text.lower()
    if "cuda out of memory" in low or "outofmemoryerror" in low:
        return "CUDA_OOM"
    if "no module named" in low or "modulenotfounderror" in low:
        return "IMPORT_ERROR"
    if "validation error" in low or "unexpected keyword" in low or "invalid" in low:
        return "INVALID_CONFIG"
    if "nan" in low or "overflow" in low:
        return "NUMERICAL_ERROR"
    if returncode == 124:
        return "TIMEOUT"
    return "PROCESS_ERROR"


def prune_run_checkpoints(run_dir: Path) -> None:
    import re

    pattern = re.compile(r"(?P<epoch>\d+)-(?P<step>\d+)")

    for directory in run_dir.rglob("checkpoints"):
        if not directory.is_dir():
            continue

        checkpoints = [
            path
            for path in directory.glob("*.ckpt")
            if path.is_file()
        ]

        if len(checkpoints) <= 2:
            continue

        keep: set[Path] = set()

        canonical_last = directory / "last.ckpt"
        if canonical_last.is_file():
            keep.add(canonical_last)

        numbered = [
            path
            for path in checkpoints
            if pattern.search(path.name)
            and "-v" not in path.stem
        ]

        if numbered:
            def score(path: Path) -> tuple[int, int, float]:
                match = pattern.search(path.name)

                if not match:
                    return (0, 0, path.stat().st_mtime)

                return (
                    int(match.group("step")),
                    int(match.group("epoch")),
                    path.stat().st_mtime,
                )

            keep.add(max(numbered, key=score))

        if not keep and checkpoints:
            keep.add(
                max(
                    checkpoints,
                    key=lambda p: p.stat().st_mtime,
                )
            )

        for checkpoint in checkpoints:
            if checkpoint not in keep:
                checkpoint.unlink()


def collect_artifacts(
    run_dir: Path,
    artifact_root: Path,
    trial_id: str,
) -> list[str]:
    import os
    import re

    pattern = re.compile(r"\d+-\d+")

    keep_names = {
        "lineage.json",
        "research_summary.json",
        "configuration.pkl",
        "dataset.pkl",
        "alias_to_model.pkl",
    }

    destination = artifact_root / trial_id
    destination.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []

    for source in run_dir.rglob("*"):
        if not source.is_file():
            continue

        should_keep = source.name in keep_names

        if (
            source.suffix.lower() in MODEL_ARTIFACT_SUFFIXES
            and "neuralforecast" in source.parts
        ):
            should_keep = True

        if (
            source.suffix.lower() == ".ckpt"
            and "checkpoints" in source.parts
            and (
                source.name == "last.ckpt"
                or (
                    pattern.search(source.name)
                    and "-v" not in source.stem
                )
            )
        ):
            should_keep = True

        if not should_keep:
            continue

        relative = source.relative_to(run_dir)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            target.unlink()

        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

        copied.append(str(target))

    manifest = []

    for artifact in destination.rglob("*"):
        if not artifact.is_file():
            continue

        if artifact.name == "artifact_manifest.json":
            continue

        manifest.append({
            "path": str(artifact),
            "sha256": hashlib.sha256(
                artifact.read_bytes()
            ).hexdigest(),
            "size_bytes": artifact.stat().st_size,
            "inode": artifact.stat().st_ino,
        })

    atomic_json(
        destination / "artifact_manifest.json",
        manifest,
    )

    return copied


def build_config(base: dict[str, Any], trial: Trial, run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg["models"] = [trial.model_id]
    cfg["model_params"] = {trial.model_id: trial.params}
    cfg.setdefault("cv", {})
    cfg["cv"].update({
        "outer_folds": args.outer_folds,
        "inner_folds": args.inner_folds,
        "test_size": args.test_size,
        "seeds": [args.seed],
    })
    cfg.setdefault("search", {})
    cfg["search"].update({
        "backend": "none",
        "trials": 1,
        "parallel_jobs": 1,
        "cpus_per_trial": args.cpu_threads,
        "gpus_per_trial": 1,
        "fail_fast": False,
        "max_consecutive_failures": 999999,
    })
    cfg.setdefault("observability", {})
    cfg["observability"].update({
        "jsonl_log": True,
        "capture_gpu": True,
        "capture_process_tree": True,
        "trace_sample_ratio": 1.0,
        "experiment_name": args.experiment_name,
    })
    cfg.setdefault("runtime", {})
    cfg["runtime"].update({
        "output": str(run_dir),
        "device": "cuda",
        "precision": args.precision,
        "deterministic": True,
        "worker_isolation": "subprocess",
        "model_timeout_seconds": args.trial_timeout,
        "resume": True,
    })
    return cfg


def run_command(cmd: list[str], log_path: Path, timeout: int, env: dict[str, str]) -> tuple[int, float, str]:
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True, env=env
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            rc = 124
    elapsed = time.monotonic() - started
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return rc, elapsed, text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--per-model", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--models", nargs="*")
    p.add_argument("--include-nixtla", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--include-foundation", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--base-config", default="configs/research_smoke.yaml")
    p.add_argument("--catalog", default="configs/model_catalog.json")
    p.add_argument("--campaign-root", default="runs/gpu-24h-campaign")
    p.add_argument("--trial-timeout", type=int, default=7200)
    p.add_argument("--validate-timeout", type=int, default=180)
    p.add_argument("--cpu-threads", type=int, default=8)
    p.add_argument("--precision", default="32")
    p.add_argument("--outer-folds", type=int, default=2)
    p.add_argument("--inner-folds", type=int, default=1)
    p.add_argument("--test-size", type=int, default=3)
    p.add_argument("--experiment-name", default="loto-gpu-24h")
    p.add_argument("--resume-campaign")
    args = p.parse_args()

    project = Path.cwd()
    base_path = project / args.base_config
    catalog_path = project / args.catalog
    if not base_path.is_file() or not catalog_path.is_file():
        raise SystemExit("Run from the loto_forecast_platform project root")

    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    catalog = read_catalog(catalog_path)
    models = choose_models(args, catalog)
    if not models:
        raise SystemExit("No catalog models selected")

    if args.resume_campaign:
        campaign = Path(args.resume_campaign)
        state = load_state(campaign / "state.json")
        trials = [Trial(**row) for row in state["trials"]]
        started_epoch = float(state["started_epoch"])
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        campaign = Path(args.campaign_root) / stamp
        campaign.mkdir(parents=True, exist_ok=False)
        trials = build_trials(models, args.per_model, args.seed)
        started_epoch = time.time()

    configs = campaign / "configs"
    runs = campaign / "runs"
    logs = campaign / "logs"
    artifacts = campaign / "saved-models"
    for d in (configs, runs, logs, artifacts):
        d.mkdir(parents=True, exist_ok=True)

    deadline = started_epoch + args.hours * 3600
    env = os.environ.copy()
    env.update({
        "CUDA_VISIBLE_DEVICES": "0",
        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        "OMP_NUM_THREADS": str(args.cpu_threads),
        "MKL_NUM_THREADS": str(args.cpu_threads),
        "OPENBLAS_NUM_THREADS": str(args.cpu_threads),
        "NUMEXPR_NUM_THREADS": str(args.cpu_threads),
        "TOKENIZERS_PARALLELISM": "false",
    })

    for trial in trials:
        if time.time() >= deadline:
            break
        if trial.status == "SUCCEEDED":
            continue

        cfg_path = configs / f"{trial.trial_id}.yaml"
        run_dir = runs / trial.trial_id
        log_path = logs / f"{trial.trial_id}.log"
        validate_log = logs / f"{trial.trial_id}.validate.log"
        cfg = build_config(base, trial, run_dir, args)
        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        trial.config_path = str(cfg_path)
        trial.run_dir = str(run_dir)
        trial.log_path = str(log_path)
        trial.status = "VALIDATING"

        atomic_json(campaign / "state.json", {
            "schema_version": "2.0.0",
            "started_at": datetime.fromtimestamp(started_epoch, timezone.utc).isoformat(),
            "started_epoch": started_epoch,
            "deadline_at": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
            "models": models,
            "trials": [asdict(t) for t in trials],
        })

        validate_cmd = ["uv", "run", "loto", "config", "validate", "--file", str(cfg_path)]
        rc, elapsed, text = run_command(validate_cmd, validate_log, args.validate_timeout, env)
        if rc != 0:
            trial.status = "INVALID_CONFIG"
            trial.returncode = rc
            trial.elapsed_seconds = elapsed
            trial.error_class = classify(text, rc)
            write_csv(campaign / "results.csv", trials)
            continue

        trial.status = "RUNNING"
        cmd = ["uv", "run", "loto", "experiment", "research", "--config", str(cfg_path)]
        rc, elapsed, text = run_command(cmd, log_path, args.trial_timeout, env)
        trial.elapsed_seconds = elapsed
        trial.returncode = rc
        if rc == 0:
            trial.status = "SUCCEEDED"
            prune_run_checkpoints(run_dir)
            trial.artifacts = collect_artifacts(
                run_dir,
                artifacts,
                trial.trial_id,
            )
        else:
            trial.status = classify(text, rc)
            trial.error_class = trial.status

        write_csv(campaign / "results.csv", trials)
        atomic_json(campaign / "state.json", {
            "schema_version": "2.0.0",
            "started_at": datetime.fromtimestamp(started_epoch, timezone.utc).isoformat(),
            "started_epoch": started_epoch,
            "deadline_at": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
            "updated_at": utcnow(),
            "models": models,
            "trials": [asdict(t) for t in trials],
        })
        counts: dict[str, int] = {}
        for t in trials:
            counts[t.status] = counts.get(t.status, 0) + 1
        print(f"[{utcnow()}] {trial.trial_id} {trial.status} {elapsed:.1f}s counts={counts}", flush=True)

    counts: dict[str, int] = {}
    for t in trials:
        counts[t.status] = counts.get(t.status, 0) + 1
    summary = {
        "schema_version": "2.0.0",
        "campaign": str(campaign),
        "started_at": datetime.fromtimestamp(started_epoch, timezone.utc).isoformat(),
        "finished_at": utcnow(),
        "deadline_at": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        "hours_budget": args.hours,
        "models": models,
        "status_counts": counts,
        "results_csv": str(campaign / "results.csv"),
        "state_json": str(campaign / "state.json"),
        "saved_models": str(artifacts),
    }
    atomic_json(campaign / "summary.json", summary)
    write_csv(campaign / "results.csv", trials)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
