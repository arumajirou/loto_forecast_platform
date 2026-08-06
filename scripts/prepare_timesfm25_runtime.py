from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.adapters.timesfm25.contracts import TimesFM25Request  # noqa: E402
from loto.timesfm25_campaign.certification_bundle import atomic_write_json  # noqa: E402
from loto.timesfm25_campaign.model_manifest import ModelManifest  # noqa: E402
from loto.timesfm25_campaign.preflight import run_preflight  # noqa: E402

DEFAULT_ENVIRONMENT = ROOT / "environments" / "timesfm25-pytorch"
DEFAULT_MANIFEST = ROOT / "configs" / "timesfm25_campaign" / "model_manifest.json"


def _load_manifest(path: Path) -> ModelManifest:
    return ModelManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _generate_lock(environment: Path, timeout: int) -> dict[str, Any]:
    command = ["uv", "lock", "--project", str(environment.resolve())]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare and verify a pinned TimesFM 2.5 runtime environment"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--generate-lock", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.output.exists() and not args.force:
        parser.error(f"output already exists: {args.output}; use --force to replace it")

    request = TimesFM25Request.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    lock_generation = None
    if args.generate_lock:
        lock_generation = _generate_lock(args.environment, args.timeout)
        if lock_generation["returncode"] != 0:
            atomic_write_json(
                args.output,
                {
                    "schema_version": 1,
                    "run_id": request.run_id,
                    "status": "FAIL",
                    "failure_reason": "UV_LOCK_GENERATION_FAILED",
                    "lock_generation": lock_generation,
                },
            )
            raise SystemExit(1)

    report = run_preflight(
        request,
        environment=args.environment,
        manifest=_load_manifest(args.manifest),
        project_root=args.project_root,
        timeout=args.timeout,
    )
    report["lock_generation"] = lock_generation
    atomic_write_json(args.output, report)
    print(f"PREFLIGHT_REPORT={args.output.resolve()}")
    print(f"STATUS={report['status']}")
    for failed in report["failed_checks"]:
        print(f"FAILED_CHECK={failed}")
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
