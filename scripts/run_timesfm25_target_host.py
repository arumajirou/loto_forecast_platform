from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.timesfm25_campaign.operator_workflow import (  # noqa: E402
    build_runner_script,
    create_deterministic_zip,
    create_request_payload,
    default_run_id,
    inspect_runtime_bundle,
    tmux_launch_command,
    tmux_session_name,
    utc_now,
    write_json,
    write_runner_script,
)

DEFAULT_TEMPLATE = ROOT / "configs" / "timesfm25_campaign" / "runtime_request.example.json"
DEFAULT_ENVIRONMENT = ROOT / "environments" / "timesfm25-pytorch"
DEFAULT_MANIFEST = ROOT / "configs" / "timesfm25_campaign" / "model_manifest.json"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "timesfm25" / "runtime-certification"
DEFAULT_OPERATOR_ROOT = ROOT / "artifacts" / "timesfm25" / "operator"
DEFAULT_ARCHIVE_ROOT = ROOT / "artifacts" / "timesfm25" / "runtime-archives"


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _tmux_alive(session_name: str, *, cwd: Path) -> bool:
    if shutil.which("tmux") is None:
        return False
    result = _run(["tmux", "has-session", "-t", session_name], cwd=cwd)
    return result.returncode == 0


def _read_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _state_path(operator_root: Path, run_id: str) -> Path:
    return operator_root.resolve() / run_id / "operator_state.json"


def _write_state(operator_root: Path, run_id: str, payload: dict[str, Any]) -> None:
    payload = {"schema_version": 1, "updated_at": utc_now(), **payload}
    write_json(_state_path(operator_root, run_id), payload)


def _preflight_command(
    args: argparse.Namespace,
    request_path: Path,
    report_path: Path,
) -> list[str]:
    command = [
        "uv",
        "run",
        "--project",
        str(args.project_root.resolve()),
        "python",
        str(args.project_root.resolve() / "scripts" / "prepare_timesfm25_runtime.py"),
        "--request",
        str(request_path),
        "--environment",
        str(args.environment.resolve()),
        "--manifest",
        str(args.manifest.resolve()),
        "--project-root",
        str(args.project_root.resolve()),
        "--output",
        str(report_path),
        "--timeout",
        str(args.preflight_timeout),
    ]
    if args.generate_lock:
        command.append("--generate-lock")
    return command


def launch(args: argparse.Namespace) -> int:
    run_id = args.run_id or default_run_id()
    session_name = tmux_session_name(run_id)
    if not args.foreground and shutil.which("tmux") is None:
        raise RuntimeError("tmux is required unless --foreground is used")
    request_payload = create_request_payload(
        args.request_template.resolve(),
        run_id=run_id,
        snapshot_path=args.snapshot,
    )
    control_dir = args.operator_root.resolve() / run_id
    run_dir = args.output_root.resolve() / run_id
    if control_dir.exists() or run_dir.exists():
        raise FileExistsError(f"run_id already exists: {run_id}")
    control_dir.mkdir(parents=True)

    request_path = control_dir / "provider_request.json"
    preflight_path = control_dir / "preflight.json"
    write_json(request_path, request_payload)
    _write_state(
        args.operator_root,
        run_id,
        {"run_id": run_id, "operator_status": "PREFLIGHT_RUNNING"},
    )

    preflight_command = _preflight_command(args, request_path, preflight_path)
    preflight = _run(preflight_command, cwd=args.project_root.resolve())
    (control_dir / "preflight.stdout.log").write_text(
        preflight.stdout,
        encoding="utf-8",
    )
    (control_dir / "preflight.stderr.log").write_text(
        preflight.stderr,
        encoding="utf-8",
    )
    report = _read_report(preflight_path)
    if preflight.returncode != 0 or report is None or report.get("status") != "PASS":
        _write_state(
            args.operator_root,
            run_id,
            {
                "run_id": run_id,
                "operator_status": "PREFLIGHT_FAILED",
                "preflight_returncode": preflight.returncode,
                "preflight_report": report,
            },
        )
        print(f"RUN_ID={run_id}")
        print("STATUS=PREFLIGHT_FAILED")
        return 1

    runner_path = control_dir / "run_runtime_certification.sh"
    runner = build_runner_script(
        project_root=args.project_root,
        request_path=request_path,
        environment=args.environment,
        output_root=args.output_root,
        control_dir=control_dir,
        timeout=args.timeout,
        preflight_timeout=args.preflight_timeout,
    )
    write_runner_script(runner_path, runner)
    runtime_summary = None
    if args.foreground:
        completed = _run(["bash", str(runner_path)], cwd=args.project_root.resolve())
        alive = False
        launch_returncode = completed.returncode
        runtime_summary = inspect_runtime_bundle(run_dir, tmux_alive=False)
        operator_status = runtime_summary["operator_status"]
    else:
        completed = _run(
            tmux_launch_command(session_name, runner_path),
            cwd=args.project_root.resolve(),
        )
        launch_returncode = completed.returncode
        alive = launch_returncode == 0 and _tmux_alive(
            session_name,
            cwd=args.project_root.resolve(),
        )
        if alive:
            operator_status = "RUNNING"
        elif launch_returncode == 0:
            runtime_summary = inspect_runtime_bundle(run_dir, tmux_alive=False)
            operator_status = runtime_summary["operator_status"]
        else:
            operator_status = "LAUNCH_FAILED"
    _write_state(
        args.operator_root,
        run_id,
        {
            "run_id": run_id,
            "operator_status": operator_status,
            "tmux_session": session_name,
            "request_path": str(request_path),
            "runtime_run_dir": str(run_dir),
            "launch_returncode": launch_returncode,
            "runtime_summary": runtime_summary,
        },
    )
    print(f"RUN_ID={run_id}")
    print(f"TMUX_SESSION={session_name}")
    print(f"OPERATOR_DIR={control_dir}")
    print(f"RUNTIME_DIR={run_dir}")
    print(f"STATUS={operator_status}")
    return launch_returncode if args.foreground else (0 if launch_returncode == 0 else 1)


def status(args: argparse.Namespace) -> int:
    session_name = tmux_session_name(args.run_id)
    alive = _tmux_alive(session_name, cwd=args.project_root.resolve())
    run_dir = args.output_root.resolve() / args.run_id
    summary = inspect_runtime_bundle(run_dir, tmux_alive=alive)
    summary["run_id"] = args.run_id
    summary["tmux_session"] = session_name
    _write_state(args.operator_root, args.run_id, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["operator_status"] not in {"CORRUPT", "FAILED"} else 1


def finalize(args: argparse.Namespace) -> int:
    session_name = tmux_session_name(args.run_id)
    if _tmux_alive(session_name, cwd=args.project_root.resolve()):
        print("STATUS=RUNNING")
        return 3
    run_dir = args.output_root.resolve() / args.run_id
    summary = inspect_runtime_bundle(run_dir, tmux_alive=False)
    operator_status = summary["operator_status"]
    if operator_status not in {"COMPLETED", "PARTIAL", "FAILED"}:
        _write_state(args.operator_root, args.run_id, summary)
        print(f"STATUS={operator_status}")
        return 1
    archive_path = args.archive_root.resolve() / f"{args.run_id}.zip"
    archive = create_deterministic_zip(run_dir, archive_path, force=args.force)
    summary["archive"] = archive
    _write_state(args.operator_root, args.run_id, summary)
    print(f"STATUS={operator_status}")
    print(f"ARCHIVE={archive['archive_path']}")
    print(f"ARCHIVE_SHA256={archive['sha256']}")
    if operator_status == "PARTIAL":
        return 2
    return 0 if operator_status == "COMPLETED" else 1


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--operator-root", type=Path, default=DEFAULT_OPERATOR_ROOT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate TimesFM 2.5 target-host certification")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch")
    _common_paths(launch_parser)
    launch_parser.add_argument("--snapshot", required=True, type=Path)
    launch_parser.add_argument("--run-id")
    launch_parser.add_argument("--request-template", type=Path, default=DEFAULT_TEMPLATE)
    launch_parser.add_argument("--environment", type=Path, default=DEFAULT_ENVIRONMENT)
    launch_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    launch_parser.add_argument("--timeout", type=int, default=3600)
    launch_parser.add_argument("--preflight-timeout", type=int, default=600)
    launch_parser.add_argument("--generate-lock", action="store_true")
    launch_parser.add_argument("--foreground", action="store_true")
    launch_parser.set_defaults(handler=launch)

    status_parser = subparsers.add_parser("status")
    _common_paths(status_parser)
    status_parser.add_argument("--run-id", required=True)
    status_parser.set_defaults(handler=status)

    finalize_parser = subparsers.add_parser("finalize")
    _common_paths(finalize_parser)
    finalize_parser.add_argument("--run-id", required=True)
    finalize_parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    finalize_parser.add_argument("--force", action="store_true")
    finalize_parser.set_defaults(handler=finalize)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "timeout", 1) < 1:
        parser.error("--timeout must be >= 1")
    if getattr(args, "preflight_timeout", 1) < 1:
        parser.error("--preflight-timeout must be >= 1")
    try:
        exit_code = args.handler(args)
    except Exception as exc:
        print("STATUS=FAILED", file=sys.stderr)
        print(f"ERROR_TYPE={type(exc).__name__}", file=sys.stderr)
        print(f"ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
