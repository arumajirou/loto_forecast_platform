from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ID = "thuml/sundial-base-128m"
REVISION = "3212e42564493f520593e5414af4367fc4b49226"
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


class CertificationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CertificationError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CertificationError(f"expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_counts(raw: str) -> tuple[int, ...]:
    values = tuple(int(token.strip()) for token in raw.split(",") if token.strip())
    if not values or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("sample counts must be non-empty and unique")
    if any(value < 1 or value > 100 for value in values):
        raise argparse.ArgumentTypeError("sample counts must be in 1..100")
    return values


def remote_allowlist(review_path: Path) -> dict[str, str]:
    review = load_json(review_path)
    expected = {
        "model_id": "sundial-base",
        "repo_id": REPO_ID,
        "revision": REVISION,
        "review_status": "APPROVED",
    }
    for key, value in expected.items():
        if review.get(key) != value:
            raise CertificationError(f"remote-code review {key} mismatch")
    rows = review.get("files")
    if not isinstance(rows, list) or not rows:
        raise CertificationError("remote-code review files are missing")
    return {
        Path(str(row["name"])).name: str(row["sha256"]).lower()
        for row in rows
        if isinstance(row, dict) and row.get("name") and row.get("sha256")
    }


def verify_snapshot(snapshot: Path, allowlist: dict[str, str]) -> dict[str, Any]:
    snapshot = snapshot.expanduser().resolve()
    if not snapshot.is_dir() or snapshot.name != REVISION:
        raise CertificationError(f"invalid pinned snapshot: {snapshot}")
    config = snapshot / "config.json"
    weights = sorted(snapshot.glob("*.safetensors")) + sorted(snapshot.glob("*.bin"))
    if not config.is_file() or not weights:
        raise CertificationError("snapshot config or weights are missing")
    actual_remote: dict[str, str] = {}
    for path in sorted(snapshot.glob("*.py")):
        digest = sha256(path)
        if path.name not in allowlist or allowlist[path.name] != digest:
            raise CertificationError(f"unreviewed or changed remote code: {path.name}")
        actual_remote[path.name] = digest
    required = {
        "configuration_sundial.py",
        "flow_loss.py",
        "modeling_sundial.py",
        "ts_generation_mixin.py",
    }
    if not required.issubset(actual_remote):
        raise CertificationError("required remote-code files are missing")
    return {
        "snapshot_path": str(snapshot),
        "config_sha256": sha256(config),
        "weight_sha256": {path.name: sha256(path) for path in weights},
        "remote_code_sha256": actual_remote,
    }


def resolve_python(root: Path) -> Path:
    if shutil.which("uv") is None:
        raise CertificationError("uv is not available")
    env_dir = root / "environments" / "sundial"
    if not (env_dir / "uv.lock").is_file():
        raise CertificationError("Sundial uv.lock is missing")
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(env_dir),
            "python",
            "-c",
            "import sys; print(sys.executable)",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise CertificationError(proc.stderr[-1000:] or "cannot resolve Sundial Python")
    path = Path(proc.stdout.strip()).resolve()
    if not path.is_file():
        raise CertificationError(f"resolved Python is missing: {path}")
    return path


def history(rows: int = 64) -> list[dict[str, float]]:
    return [
        {
            f"n{position}": float(((row * (position + 2)) + position) % 37 + 1)
            for position in range(1, 8)
        }
        for row in range(rows)
    ]


def flatten(value: Any) -> list[float]:
    if isinstance(value, list):
        result: list[float] = []
        for item in value:
            result.extend(flatten(item))
        return result
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    raise CertificationError("prediction payload contains a non-numeric value")


def gpu_processes() -> dict[int, int]:
    proc = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[int, int] = {}
    if proc.returncode != 0:
        return result
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        try:
            result[int(parts[0])] = int(float(parts[1]))
        except (IndexError, ValueError):
            continue
    return result


def validate_response(
    response: dict[str, Any],
    *,
    pid: int,
    device: str,
    num_samples: int,
    external_seen: bool,
    external_peak_mib: int,
) -> list[str]:
    reasons: list[str] = []
    if response.get("status") != "OK":
        return [f"STATUS_{response.get('status', 'MISSING')}"]
    if response.get("provider_version") != 2:
        reasons.append("PROVIDER_VERSION_MISMATCH")
    if response.get("samples_shape") != [7, num_samples, 1]:
        reasons.append("SAMPLE_SHAPE_MISMATCH")
    try:
        samples = flatten(response.get("samples"))
        points = flatten(response.get("predictions"))
        if len(samples) != 7 * num_samples or not all(map(math.isfinite, samples)):
            reasons.append("INVALID_SAMPLES")
        if len(points) != 7 or not all(map(math.isfinite, points)):
            reasons.append("INVALID_POINTS")
    except CertificationError:
        reasons.append("NON_NUMERIC_PREDICTION")
    if response.get("quantile_source") != "EMPIRICAL_FROM_GENERATED_SAMPLES":
        reasons.append("QUANTILE_SOURCE_MISMATCH")
    gpu = response.get("gpu_evidence")
    if not isinstance(gpu, dict):
        return [*reasons, "GPU_EVIDENCE_MISSING"]
    if gpu.get("cpu_fallback") is not False:
        reasons.append("CPU_FALLBACK")
    if device == "cpu":
        if gpu.get("execution_device") != "cpu" or gpu.get("gpu_used") is not False:
            reasons.append("CPU_SMOKE_DEVICE_MISMATCH")
    else:
        if gpu.get("execution_device") != "cuda" or gpu.get("gpu_used") is not True:
            reasons.append("CUDA_NOT_OBSERVED")
        if gpu.get("gpu_pid") != pid:
            reasons.append("INTERNAL_GPU_PID_MISMATCH")
        if int(gpu.get("peak_vram_bytes") or 0) <= 0:
            reasons.append("INTERNAL_VRAM_NOT_OBSERVED")
        if not external_seen:
            reasons.append("EXTERNAL_GPU_PID_NOT_SEEN")
        if external_peak_mib <= 0:
            reasons.append("EXTERNAL_VRAM_NOT_OBSERVED")
    return reasons


def run_case(
    *,
    root: Path,
    python: Path,
    output: Path,
    snapshot: Path,
    allowlist: dict[str, str],
    name: str,
    device: str,
    num_samples: int,
    seed: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    case_dir = output / "cases" / name
    case_dir.mkdir(parents=True)
    request_path = case_dir / "request.json"
    response_path = case_dir / "response.json"
    request = {
        "schema_version": 1,
        "model_id": "sundial-base",
        "repo_id": REPO_ID,
        "revision": REVISION,
        "snapshot_path": str(snapshot),
        "local_files_only": True,
        "device": device,
        "dtype": "float32",
        "history": history(),
        "prediction_length": 1,
        "num_samples": num_samples,
        "quantile_levels": list(QUANTILES),
        "point_strategy": "median",
        "revin": True,
        "seed": seed,
        "approved_remote_code_sha256": allowlist,
    }
    write_json(request_path, request)
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    if device == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""
    started = time.monotonic()
    with (
        (case_dir / "stdout.log").open("w") as stdout,
        (case_dir / "stderr.log").open("w") as stderr,
    ):
        proc = subprocess.Popen(
            [
                str(python),
                str(root / "scripts" / "run_sundial_provider.py"),
                "--request",
                str(request_path),
                "--response",
                str(response_path),
            ],
            cwd=root,
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        monitor: list[dict[str, Any]] = []
        seen = False
        peak = 0
        timed_out = False
        while proc.poll() is None:
            if time.monotonic() - started > timeout_seconds:
                timed_out = True
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            processes = gpu_processes()
            used = processes.get(proc.pid, 0)
            seen = seen or proc.pid in processes
            peak = max(peak, used)
            monitor.append({"timestamp_utc": utc_now(), "pid": proc.pid, "used_mib": used})
            time.sleep(0.1)
        return_code = proc.wait()
    write_json(
        case_dir / "gpu-monitor.json",
        {"pid": proc.pid, "external_seen": seen, "external_peak_mib": peak, "rows": monitor},
    )
    response: dict[str, Any] = {}
    response_read_error: str | None = None
    if response_path.is_file():
        try:
            response = load_json(response_path)
        except CertificationError as exc:
            response_read_error = str(exc)
    reasons = validate_response(
        response,
        pid=proc.pid,
        device=device,
        num_samples=num_samples,
        external_seen=seen,
        external_peak_mib=peak,
    )
    if response_read_error is not None:
        reasons.append("INVALID_RESPONSE_JSON")
    if timed_out:
        reasons.append("CASE_TIMEOUT")
    if return_code != 0:
        reasons.append(f"RETURN_CODE_{return_code}")
    return {
        "name": name,
        "device": device,
        "num_samples": num_samples,
        "seed": seed,
        "passed": not reasons,
        "reasons": reasons,
        "return_code": return_code,
        "duration_seconds": time.monotonic() - started,
        "pid": proc.pid,
        "external_gpu_pid_seen": seen,
        "external_peak_vram_mib": peak,
        "request_sha256": sha256(request_path),
        "response_sha256": sha256(response_path) if response_path.is_file() else None,
        "response_read_error": response_read_error,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
    }


def compare_replays(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    a = flatten(left.get("samples"))
    b = flatten(right.get("samples"))
    if len(a) != len(b):
        return {"classification": "SHAPE_MISMATCH", "passed": False}
    exact = a == b
    close = all(math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-7) for x, y in zip(a, b))
    return {
        "classification": "EXACT" if exact else "NUMERIC_CLOSE" if close else "DIVERGENT",
        "passed": exact or close,
        "sample_count": len(a),
        "maximum_absolute_difference": max((abs(x - y) for x, y in zip(a, b)), default=0.0),
    }


def git_value(root: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def write_checksums(root: Path) -> None:
    target = root / "SHA256SUMS"
    files = sorted(path for path in root.rglob("*") if path.is_file() and path != target)
    target.write_text(
        "\n".join(f"{sha256(path)}  {path.relative_to(root)}" for path in files) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify Sundial provider v2")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/sundial-provider-v2"))
    parser.add_argument("--sample-counts", type=parse_counts, default=(1, 3, 20, 50, 100))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replay-samples", type=int, default=20)
    parser.add_argument("--case-timeout", type=int, default=1800)
    args = parser.parse_args()

    root = args.repo_root.expanduser().resolve()
    review_path = root / "audit/tsfm-runtime/sundial-base/remote-code-review.json"
    allowlist = remote_allowlist(review_path)
    snapshot_evidence = verify_snapshot(args.snapshot, allowlist)
    snapshot = Path(snapshot_evidence["snapshot_path"])
    python = resolve_python(root)
    if shutil.which("nvidia-smi") is None:
        raise CertificationError("nvidia-smi is not available")

    run_id = f"sundial-v2-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output = (root / args.output_root / run_id).resolve()
    output.mkdir(parents=True)
    (output.parent / "LATEST").write_text(str(output) + "\n", encoding="utf-8")
    write_json(
        output / "environment.json",
        {
            "run_id": run_id,
            "started_at_utc": utc_now(),
            "git_commit": git_value(root, "rev-parse", "HEAD"),
            "git_branch": git_value(root, "branch", "--show-current"),
            "git_status_porcelain": git_value(root, "status", "--porcelain=v1"),
            "platform": platform.platform(),
            "python": sys.version,
            "sundial_python": str(python),
            "snapshot": snapshot_evidence,
            "remote_code_review_sha256": sha256(review_path),
            "sundial_lock_sha256": sha256(root / "environments/sundial/uv.lock"),
            "runner_sha256": sha256(root / "scripts/run_sundial_provider.py"),
            "harness_sha256": sha256(Path(__file__).resolve()),
        },
    )

    cases = [
        run_case(
            root=root,
            python=python,
            output=output,
            snapshot=snapshot,
            allowlist=allowlist,
            name="cpu-smoke-ns001",
            device="cpu",
            num_samples=1,
            seed=args.seed,
            timeout_seconds=args.case_timeout,
        )
    ]
    for count in args.sample_counts:
        cases.append(
            run_case(
                root=root,
                python=python,
                output=output,
                snapshot=snapshot,
                allowlist=allowlist,
                name=f"cuda-ns{count:03d}",
                device="cuda",
                num_samples=count,
                seed=args.seed,
                timeout_seconds=args.case_timeout,
            )
        )
    for name in ("cuda-replay-a", "cuda-replay-b"):
        cases.append(
            run_case(
                root=root,
                python=python,
                output=output,
                snapshot=snapshot,
                allowlist=allowlist,
                name=name,
                device="cuda",
                num_samples=args.replay_samples,
                seed=args.seed,
                timeout_seconds=args.case_timeout,
            )
        )

    replay_paths = [
        output / "cases" / name / "response.json" for name in ("cuda-replay-a", "cuda-replay-b")
    ]
    if all(path.is_file() for path in replay_paths):
        try:
            replay = compare_replays(load_json(replay_paths[0]), load_json(replay_paths[1]))
        except CertificationError as exc:
            replay = {
                "classification": "INVALID_RESPONSE",
                "passed": False,
                "reason": str(exc),
            }
    else:
        replay = {"classification": "NOT_EVALUATED", "passed": False}
    write_json(output / "reproducibility.json", replay)
    status = "PASS" if all(case["passed"] for case in cases) and replay["passed"] else "FAIL"
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "finished_at_utc": utc_now(),
        "repo_id": REPO_ID,
        "revision": REVISION,
        "sample_counts": list(args.sample_counts),
        "seed": args.seed,
        "case_timeout_seconds": args.case_timeout,
        "cases": cases,
        "reproducibility": replay,
        "formal_gpu_certification": status == "PASS",
        "cpu_fallback_allowed": False,
    }
    write_json(output / "certification-summary.json", summary)
    write_json(
        output / "ARTIFACT_MANIFEST.json",
        {
            "run_id": run_id,
            "status": status,
            "case_directories": [case["name"] for case in cases],
            "required_files": [
                "environment.json",
                "certification-summary.json",
                "reproducibility.json",
                "SHA256SUMS",
            ],
        },
    )
    (output / "status.txt").write_text(
        f"SUNDIAL_PROVIDER_V2_CERTIFICATION={status}\nRUN_DIR={output}\n",
        encoding="utf-8",
    )
    write_checksums(output)
    print(f"SUNDIAL_PROVIDER_V2_CERTIFICATION={status}")
    print(f"RUN_DIR={output}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CertificationError as exc:
        print(f"SUNDIAL_PROVIDER_V2_CERTIFICATION=BLOCKED\nREASON={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
