from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from loto.autogluon_campaign.runtime_certification import (
    CertificationStatus,
    RuntimeCertificationConfig,
    run_runtime_certification,
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _scan_tree(root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            errors.append(f"evidence tree contains a symbolic link: {relative}")
        elif stat.S_ISREG(mode):
            files.append(path)
        elif stat.S_ISDIR(mode):
            continue
        else:
            errors.append(f"evidence tree contains a special file: {relative}")
    return files, errors


def _effective_status(payload: dict[str, Any], evidence_errors: list[str]) -> str:
    scenario_count = int(payload.get("scenario_count", 0))
    verified_count = int(payload.get("verified_count", 0))
    failed_count = int(payload.get("failed_count", 0))
    blocked_count = int(payload.get("blocked_count", 0))
    if failed_count > 0 or evidence_errors:
        return CertificationStatus.FAILED.value
    if scenario_count > 0 and verified_count == scenario_count:
        return CertificationStatus.VERIFIED.value
    if scenario_count > 0 and blocked_count == scenario_count:
        return CertificationStatus.BLOCKED_RUNTIME.value
    if verified_count > 0 and blocked_count > 0:
        return CertificationStatus.PARTIALLY_VERIFIED.value
    return CertificationStatus.FAILED.value


def _parse_sha256sums(path: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    errors: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            errors.append(f"invalid SHA256SUMS line {line_number}")
            continue
        digest, relative = match.groups()
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            errors.append(f"unsafe SHA256SUMS path: {relative}")
            continue
        if relative in entries:
            errors.append(f"duplicate SHA256SUMS path: {relative}")
            continue
        entries[relative] = digest
    return entries, errors


def verify_guarded_output(output_dir: Path) -> tuple[str, ...]:
    root = output_dir.resolve()
    errors: list[str] = []
    report_path = root / "RUNTIME_CERTIFICATION_REPORT.json"
    sums_path = root / "SHA256SUMS"
    if not report_path.is_file():
        errors.append("missing RUNTIME_CERTIFICATION_REPORT.json")
    if not sums_path.is_file():
        errors.append("missing SHA256SUMS")
    if errors:
        return tuple(errors)

    files, tree_errors = _scan_tree(root)
    errors.extend(tree_errors)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid runtime certification report: {exc}")
    else:
        embedded = report.pop("report_sha256", None)
        if not isinstance(embedded, str) or re.fullmatch(r"[0-9a-f]{64}", embedded) is None:
            errors.append("report_sha256 is missing or invalid")
        elif _sha256_bytes(_canonical_json(report)) != embedded:
            errors.append("report_sha256 mismatch")

    entries, manifest_errors = _parse_sha256sums(sums_path)
    errors.extend(manifest_errors)
    expected = {
        path.relative_to(root).as_posix()
        for path in files
        if path.name != "SHA256SUMS"
    }
    if set(entries) != expected:
        missing = sorted(expected - set(entries))
        extra = sorted(set(entries) - expected)
        if missing:
            errors.append(f"SHA256SUMS is missing files: {missing}")
        if extra:
            errors.append(f"SHA256SUMS contains unknown files: {extra}")
    for relative, expected_hash in entries.items():
        target = root / PurePosixPath(relative)
        try:
            mode = target.lstat().st_mode
        except FileNotFoundError:
            errors.append(f"SHA256SUMS target is missing: {relative}")
            continue
        if not stat.S_ISREG(mode):
            errors.append(f"SHA256SUMS target is not a regular file: {relative}")
            continue
        if _sha256_file(target) != expected_hash:
            errors.append(f"SHA-256 mismatch: {relative}")
    return tuple(errors)


def finalize_guarded_output(output_dir: Path) -> dict[str, Any]:
    root = output_dir.resolve()
    report_path = root / "RUNTIME_CERTIFICATION_REPORT.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload.pop("report_sha256", None)
    _files, tree_errors = _scan_tree(root)
    payload["status"] = _effective_status(payload, tree_errors)
    payload["p11_evidence_errors"] = tree_errors
    payload["p11_verification_id"] = (
        datetime.now(timezone.utc).strftime("autogluon-p11-%Y%m%dT%H%M%S.%fZ")
        + f"-pid{os.getpid()}"
    )
    payload["p11_guard_schema_version"] = 1
    payload["report_sha256"] = _sha256_bytes(_canonical_json(payload))
    _write_json_atomic(report_path, payload)

    files, post_errors = _scan_tree(root)
    if post_errors != tree_errors:
        raise RuntimeError("evidence tree changed while P11 guard was finalizing")
    sums = [
        f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in files
        if path.name != "SHA256SUMS"
    ]
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    verification_errors = verify_guarded_output(root)
    unexpected = [error for error in verification_errors if error not in tree_errors]
    if unexpected:
        raise RuntimeError("P11 guarded evidence verification failed: " + "; ".join(unexpected))
    return payload


def run_guarded_certification(config: RuntimeCertificationConfig) -> dict[str, Any]:
    run_runtime_certification(config)
    return finalize_guarded_output(config.output_dir)


def _provider_command(repo_root: Path) -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--project",
        str(repo_root / "environments" / "autogluon-timeseries"),
        "--locked",
        "python",
        str(repo_root / "scripts" / "run_autogluon_timeseries_provider.py"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or verify guarded AutoGluon runtime certification evidence."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-output", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--scenario", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify_output is not None:
        if args.output_dir is not None or args.scenario:
            raise SystemExit("--verify-output cannot be combined with run options")
        errors = verify_guarded_output(args.verify_output)
        print(f"AUTOGLUON_P11_VERIFY_STATUS={'PASS' if not errors else 'FAIL'}")
        for error in errors:
            print(f"AUTOGLUON_P11_VERIFY_ERROR={error}")
        return 0 if not errors else 3
    if args.output_dir is None:
        raise SystemExit("--output-dir is required unless --verify-output is used")
    repo_root = args.repo_root.resolve()
    payload = run_guarded_certification(
        RuntimeCertificationConfig(
            repo_root=repo_root,
            output_dir=args.output_dir,
            provider_command=_provider_command(repo_root),
            timeout_seconds=args.timeout_seconds,
            scenario_ids=tuple(args.scenario),
        )
    )
    status = str(payload["status"])
    print(f"AUTOGLUON_P11_STATUS={status}")
    print(f"AUTOGLUON_P11_RUN_ID={payload['run_id']}")
    print(f"AUTOGLUON_P11_VERIFICATION_ID={payload['p11_verification_id']}")
    print(f"AUTOGLUON_P11_REPORT_SHA256={payload['report_sha256']}")
    print(f"AUTOGLUON_P11_OUTPUT={Path(args.output_dir).resolve()}")
    if status == CertificationStatus.VERIFIED.value:
        return 0
    if status == CertificationStatus.PARTIALLY_VERIFIED.value:
        return 1
    if status == CertificationStatus.BLOCKED_RUNTIME.value:
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
