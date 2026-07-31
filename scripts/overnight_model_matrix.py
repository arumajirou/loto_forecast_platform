#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:
    raise SystemExit(f"PyYAML is required: {exc}") from exc

PROJECT = Path.cwd()
DEFAULT_BASE = PROJECT / "configs" / "research_smoke.yaml"
DEFAULT_CATALOG = PROJECT / "configs" / "model_catalog.json"

# Bounded, auditable value sets. Continuous parameters cannot be literally exhausted.
COMMON_GRID: dict[str, list[Any]] = {
    "input_size": [8, 16, 32, 64],
    "max_steps": [30, 100, 300],
    "learning_rate": [1e-4, 3e-4, 1e-3],
    "batch_size": [16, 32, 64],
}

# Conservative model-specific additions. Unsupported combinations are rejected by
# config validation or isolated as failed runs, without stopping the campaign.
MODEL_GRIDS: dict[str, dict[str, list[Any]]] = {
    "nf-dlinear": {},
    "nf-nlinear": {},
    "nf-nhits": {
        "n_blocks": [[1, 1, 1], [2, 2, 2]],
        "mlp_units": [[[64, 64], [64, 64], [64, 64]], [[128, 128], [128, 128], [128, 128]]],
    },
    "nf-tide": {
        "hidden_size": [64, 128],
        "decoder_output_dim": [16, 32],
    },
    "nf-nbeats": {
        "stack_types": [["identity", "identity"], ["trend", "seasonality"]],
    },
    "nf-rnn": {"hidden_size": [64, 128]},
    "nf-lstm": {"hidden_size": [64, 128]},
    "nf-gru": {"hidden_size": [64, 128]},
    "nf-deepar": {"hidden_size": [64, 128]},
    "nf-tft": {"hidden_size": [64, 128]},
    "nf-tsmixer": {"n_block": [1, 2], "ff_dim": [32, 64]},
}

PROFILE_LIMITS = {
    "smoke": {"common_keys": ["input_size", "max_steps"], "max_per_model": 4},
    "overnight": {
        "common_keys": ["input_size", "max_steps", "learning_rate", "batch_size"],
        "max_per_model": 36,
    },
    "exhaustive": {
        "common_keys": ["input_size", "max_steps", "learning_rate", "batch_size"],
        "max_per_model": 10_000,
    },
}


@dataclass
class RunResult:
    run_index: int
    run_name: str
    model_id: str
    status: str
    return_code: int | None
    elapsed_seconds: float
    config_path: str
    output_dir: str
    log_path: str
    params: dict[str, Any]
    started_at: str
    finished_at: str
    error: str | None = None
    timed_out: bool = False


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in value)


def sha12(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def read_catalog(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("models") or payload.get("catalog") or payload.get("entries") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
    else:
        rows = []

    model_ids: list[str] = []
    for row in rows:
        if isinstance(row, str):
            model_ids.append(row)
            continue
        if not isinstance(row, dict):
            continue
        model_id = row.get("model_id") or row.get("id") or row.get("name")
        available = row.get("available", row.get("enabled", True))
        if model_id and available is not False:
            model_ids.append(str(model_id))
    return sorted(set(model_ids))


def product_dict(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return [{}]
    keys = list(grid)
    return [
        dict(zip(keys, values, strict=False))
        for values in itertools.product(*(grid[k] for k in keys))
    ]


def build_matrix(
    models: list[str], profile: str, max_runs: int
) -> list[tuple[str, dict[str, Any]]]:
    rules = PROFILE_LIMITS[profile]
    common = {k: COMMON_GRID[k] for k in rules["common_keys"]}
    matrix: list[tuple[str, dict[str, Any]]] = []

    for model in models:
        merged = dict(common)
        merged.update(MODEL_GRIDS.get(model, {}))
        combos = product_dict(merged)

        # Deterministic spread if capped: keep first, last, then evenly spaced entries.
        cap = min(len(combos), int(rules["max_per_model"]))
        if len(combos) > cap:
            if cap <= 1:
                combos = combos[:cap]
            else:
                indices = sorted(set(round(i * (len(combos) - 1) / (cap - 1)) for i in range(cap)))
                combos = [combos[i] for i in indices]

        for params in combos:
            matrix.append((model, params))
            if len(matrix) >= max_runs:
                return matrix
    return matrix


def write_yaml(
    base: dict[str, Any],
    model: str,
    params: dict[str, Any],
    cfg_path: Path,
    output_dir: Path,
    device: str,
    seed: int,
) -> None:
    cfg = json.loads(json.dumps(base))
    cfg["models"] = [model]
    cfg.setdefault("model_params", {})
    cfg["model_params"][model] = params

    cfg.setdefault("cv", {})
    cfg["cv"]["outer_folds"] = 1
    cfg["cv"]["test_size"] = 1
    cfg["cv"]["seeds"] = [seed]

    cfg.setdefault("search", {})
    cfg["search"]["backend"] = "none"

    cfg.setdefault("runtime", {})
    cfg["runtime"]["device"] = device
    cfg["runtime"]["precision"] = "32"
    cfg["runtime"]["output"] = str(output_dir)
    cfg["runtime"]["resume"] = False

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")


def run_cmd(
    cmd: list[str], cwd: Path, log_path: Path, timeout: int
) -> tuple[int, float, bool, str | None]:
    started = time.monotonic()
    timed_out = False
    error = None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            error = f"timeout after {timeout}s"
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=20)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
            rc = 124
    return rc, time.monotonic() - started, timed_out, error


def gpu_sampler(stop: threading.Event, output: Path, interval: int = 10) -> None:
    if shutil.which("nvidia-smi") is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    header_written = output.exists() and output.stat().st_size > 0
    fields = (
        "timestamp,index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"
    )
    while not stop.is_set():
        cmd = [
            "nvidia-smi",
            f"--query-gpu={fields}",
            "--format=csv,noheader,nounits",
        ]
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if cp.returncode == 0:
            with output.open("a", encoding="utf-8") as f:
                if not header_written:
                    f.write(fields + "\n")
                    header_written = True
                f.write(cp.stdout)
        stop.wait(interval)


def classify(log_path: Path, rc: int, timed_out: bool) -> tuple[str, str | None]:
    if timed_out:
        return "TIMEOUT", "timeout"
    text = log_path.read_text(encoding="utf-8", errors="replace")[-200_000:]
    if rc == 0:
        return "SUCCEEDED", None
    patterns = [
        ("CUDA_OOM", ["CUDA out of memory", "OutOfMemoryError"]),
        ("INVALID_CONFIG", ["validation error", "invalid config", "unexpected keyword argument"]),
        ("IMPORT_ERROR", ["ModuleNotFoundError", "ImportError"]),
        ("DATA_ERROR", ["FileNotFoundError", "No such file or directory"]),
        ("NUMERICAL_ERROR", ["nan", "NaN", "inf", "overflow"]),
    ]
    lower = text.lower()
    for name, needles in patterns:
        if any(n.lower() in lower for n in needles):
            return name, next(n for n in needles if n.lower() in lower)
    return "FAILED", f"return_code={rc}"


def execute_one(
    index: int,
    model: str,
    params: dict[str, Any],
    args: argparse.Namespace,
    base: dict[str, Any],
    campaign: Path,
) -> RunResult:
    fingerprint = sha12({"model": model, "params": params, "seed": args.seed})
    run_name = f"{index:05d}-{slug(model)}-{fingerprint}"
    cfg_path = campaign / "configs" / f"{run_name}.yaml"
    out_dir = campaign / "runs" / run_name
    log_path = campaign / "logs" / f"{run_name}.log"
    write_yaml(base, model, params, cfg_path, out_dir, args.device, args.seed)

    started_at = now_iso()

    # Validate first. Unsupported args fail cheaply and are recorded.
    validate_log = campaign / "logs" / f"{run_name}.validate.log"
    vrc, velapsed, vto, verr = run_cmd(
        ["uv", "run", "loto", "config", "validate", "--file", str(cfg_path)],
        PROJECT,
        validate_log,
        min(args.timeout, 300),
    )
    if vrc != 0:
        status, error = classify(validate_log, vrc, vto)
        return RunResult(
            index,
            run_name,
            model,
            "VALIDATION_" + status,
            vrc,
            velapsed,
            str(cfg_path),
            str(out_dir),
            str(validate_log),
            params,
            started_at,
            now_iso(),
            error or verr,
            vto,
        )

    rc, elapsed, timed_out, run_error = run_cmd(
        ["uv", "run", "loto", "experiment", "research", "--config", str(cfg_path)],
        PROJECT,
        log_path,
        args.timeout,
    )
    status, classified_error = classify(log_path, rc, timed_out)
    return RunResult(
        index,
        run_name,
        model,
        status,
        rc,
        elapsed,
        str(cfg_path),
        str(out_dir),
        str(log_path),
        params,
        started_at,
        now_iso(),
        classified_error or run_error,
        timed_out,
    )


def write_results(
    campaign: Path, results: list[RunResult], matrix_count: int, args: argparse.Namespace
) -> None:
    ordered = sorted(results, key=lambda r: r.run_index)
    rows = []
    for r in ordered:
        row = asdict(r)
        row["params"] = json.dumps(r.params, sort_keys=True, ensure_ascii=False)
        rows.append(row)

    csv_path = campaign / "results.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    counts: dict[str, int] = {}
    for r in ordered:
        counts[r.status] = counts.get(r.status, 0) + 1

    summary = {
        "schema_version": "1.0.0",
        "campaign": str(campaign),
        "matrix_count": matrix_count,
        "completed": len(ordered),
        "status_counts": counts,
        "parallel": args.parallel,
        "timeout_seconds": args.timeout,
        "device": args.device,
        "seed": args.seed,
        "started_at": args.started_at,
        "finished_at": now_iso(),
        "results_csv": str(csv_path),
        "gpu_samples": str(campaign / "gpu_samples.csv"),
    }
    (campaign / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    failures = [r for r in ordered if r.status != "SUCCEEDED"]
    md = [
        "# Overnight model matrix report",
        "",
        f"- Campaign: `{campaign}`",
        f"- Matrix: {matrix_count}",
        f"- Completed: {len(ordered)}",
        f"- Status: `{json.dumps(counts, ensure_ascii=False)}`",
        "",
        "## Failures",
        "",
    ]
    if not failures:
        md.append("No failures.")
    else:
        md.append("| Run | Model | Status | Error | Log |")
        md.append("|---|---|---|---|---|")
        for r in failures[:500]:
            md.append(
                f"| {r.run_name} | {r.model_id} | {r.status} | {r.error or ''} | `{r.log_path}` |"
            )
    (campaign / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-config", default=str(DEFAULT_BASE))
    p.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    p.add_argument("--profile", choices=PROFILE_LIMITS, default="overnight")
    p.add_argument("--models", nargs="*", default=None)
    p.add_argument("--parallel", type=int, default=2)
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--max-runs", type=int, default=500)
    p.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--campaign-root", default="runs/overnight-model-matrix")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    args.started_at = now_iso()

    if not (PROJECT / "pyproject.toml").exists():
        raise SystemExit("Run from the loto_forecast_platform repository root.")

    base_path = Path(args.base_config)
    catalog_path = Path(args.catalog)
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))

    available = read_catalog(catalog_path)

    # Explicitly supplied model IDs are authoritative. Some runtime/plugin
    # models are implemented and executable even when absent from the static
    # model catalog. Unsupported IDs will be rejected by config validation and
    # recorded without stopping the campaign.
    if args.models:
        models = sorted(set(args.models))
    else:
        models = available

    if not models:
        raise SystemExit("No models were selected.")

    matrix = build_matrix(models, args.profile, args.max_runs)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    campaign = Path(args.campaign_root) / stamp
    campaign.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "1.0.0",
        "profile": args.profile,
        "available_models": available,
        "selected_models": models,
        "matrix_count": len(matrix),
        "parallel": args.parallel,
        "timeout": args.timeout,
        "device": args.device,
        "seed": args.seed,
        "matrix": [
            {"index": i, "model_id": model, "params": params}
            for i, (model, params) in enumerate(matrix, 1)
        ],
    }
    (campaign / "matrix.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in manifest.items() if k != "matrix"}, indent=2, ensure_ascii=False
        )
    )
    print(f"CAMPAIGN={campaign}")

    if args.dry_run:
        return 0

    stop = threading.Event()
    sampler = threading.Thread(
        target=gpu_sampler, args=(stop, campaign / "gpu_samples.csv"), daemon=True
    )
    sampler.start()

    results: list[RunResult] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
            futures = {
                pool.submit(execute_one, i, model, params, args, base, campaign): i
                for i, (model, params) in enumerate(matrix, 1)
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as exc:
                    i = futures[future]
                    model, params = matrix[i - 1]
                    result = RunResult(
                        i,
                        f"{i:05d}-{slug(model)}-internal",
                        model,
                        "HARNESS_ERROR",
                        None,
                        0.0,
                        "",
                        "",
                        "",
                        params,
                        now_iso(),
                        now_iso(),
                        f"{type(exc).__name__}: {exc}",
                        False,
                    )
                results.append(result)
                print(
                    f"[{len(results)}/{len(matrix)}] {result.status:20s} "
                    f"{result.model_id:24s} {result.elapsed_seconds:8.1f}s "
                    f"{result.run_name}",
                    flush=True,
                )
                write_results(campaign, results, len(matrix), args)
    finally:
        stop.set()
        sampler.join(timeout=5)
        write_results(campaign, results, len(matrix), args)

    failed = sum(r.status != "SUCCEEDED" for r in results)
    print(f"COMPLETED={len(results)} FAILED={failed}")
    print(f"REPORT={campaign / 'REPORT.md'}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
