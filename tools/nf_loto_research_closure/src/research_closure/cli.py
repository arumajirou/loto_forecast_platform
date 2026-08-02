from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .core import (
    create_closure_package,
    create_shadow_lock,
    verify_sha256sums,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="loto-research")
    sub = root.add_subparsers(dest="command", required=True)

    close = sub.add_parser("close", help="Create a research closure package")
    close.add_argument("--project-root", type=Path, default=Path.cwd())
    close.add_argument("--artifact-root", type=Path, required=True)
    close.add_argument("--data", type=Path, required=True)
    close.add_argument("--output", type=Path)
    close.add_argument("--allow-missing-stages", action="store_true")
    close.add_argument("--zip", action="store_true", dest="make_zip")

    lock = sub.add_parser("shadow-lock", help="Lock four shadow predictions")
    lock.add_argument("--project-root", type=Path, default=Path.cwd())
    lock.add_argument("--data", type=Path, required=True)
    lock.add_argument("--target-ds", required=True)
    lock.add_argument("--output", type=Path, required=True)
    lock.add_argument("--seed", type=int, default=20260802)

    verify = sub.add_parser("verify", help="Verify package SHA256SUMS")
    verify.add_argument("package", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "close":
        output = args.output or (
            args.project_root
            / "releases"
            / f"numbers3-n1-research-closure-{datetime.now():%Y%m%d-%H%M%S}"
        )
        closure_result = create_closure_package(
            project_root=args.project_root,
            artifact_root=args.artifact_root,
            data_path=args.data,
            output_dir=output,
            require_all=not args.allow_missing_stages,
        )
        payload = asdict(closure_result)
        if args.make_zip:
            archive = shutil.make_archive(str(output), "zip", output.parent, output.name)
            payload["zip"] = archive
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "shadow-lock":
        lock_result = create_shadow_lock(
            project_root=args.project_root,
            data_path=args.data,
            output_dir=args.output,
            target_ds=args.target_ds,
            seed=args.seed,
        )
        print(
            json.dumps(
                asdict(lock_result),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    failures = verify_sha256sums(args.package)
    if failures:
        print(json.dumps({"status": "FAIL", "files": failures}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "package": str(args.package)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
