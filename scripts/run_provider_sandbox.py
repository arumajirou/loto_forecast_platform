#!/usr/bin/env python3
"""Operator CLI for provider sandbox contract validation and bounded execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from loto.provider_sandbox import (
    BackendEvidence,
    EffectiveSandboxEvidence,
    SandboxArgvPlan,
    SandboxBackend,
    SandboxExecutionRequest,
    SandboxPolicy,
    SandboxProcessRunner,
    build_argv_plan,
    verify_effective_evidence,
    validate_policy_paths,
    verify_evidence_bundle,
)
from loto.provider_sandbox.canonical import canonical_json, parse_json_object


def _load_model(path: Path, model_type: type):
    data = parse_json_object(path.read_text(encoding="utf-8"))
    return model_type.model_validate_json(canonical_json(data))


class LocalPathInspector:
    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def is_symlink(self, path: str) -> bool:
        return Path(path).is_symlink()

    def is_directory(self, path: str) -> bool:
        return Path(path).is_dir()


def _write_json(value: object) -> None:
    sys.stdout.write(canonical_json(value) + "\n")


def command_validate_policy(args: argparse.Namespace) -> int:
    policy = _load_model(args.policy, SandboxPolicy)
    if args.check_host_paths:
        validate_policy_paths(policy, LocalPathInspector())
    _write_json({"status": "PASS", "policy_sha256": policy.policy_sha256})
    return 0


def command_plan(args: argparse.Namespace) -> int:
    policy = _load_model(args.policy, SandboxPolicy)
    validate_policy_paths(policy, LocalPathInspector())
    request = _load_model(args.request, SandboxExecutionRequest)
    backend = _load_model(args.backend_evidence, BackendEvidence)
    plan = build_argv_plan(policy, request, backend)
    _write_json(plan)
    return 0


def command_verify_effective(args: argparse.Namespace) -> int:
    policy = _load_model(args.policy, SandboxPolicy)
    request = _load_model(args.request, SandboxExecutionRequest)
    effective = _load_model(args.effective, EffectiveSandboxEvidence)
    report = verify_effective_evidence(policy, request, effective)
    _write_json(report)
    return 0 if report.verified else 1


def command_execute_plan(args: argparse.Namespace) -> int:
    plan = _load_model(args.plan, SandboxArgvPlan)
    if not args.test_only_confirm_no_security_certification:
        raise ValueError("execute-plan requires explicit test-only acknowledgment")
    if plan.backend != SandboxBackend.NONE:
        raise ValueError("foundation execute-plan supports NONE test fixtures only")
    runner = SandboxProcessRunner()
    result = runner.run(
        plan,
        timeout_seconds=args.timeout_seconds,
        output_limit_bytes=args.output_limit_bytes,
        environment={},
    )
    _write_json(result)
    return 0 if result.outcome.value == "SUCCEEDED" else 1


def command_verify_bundle(args: argparse.Namespace) -> int:
    _write_json(verify_evidence_bundle(args.bundle))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate-policy")
    validate.add_argument("--policy", type=Path, required=True)
    validate.add_argument("--check-host-paths", action="store_true")
    validate.set_defaults(handler=command_validate_policy)

    plan = subcommands.add_parser("plan")
    plan.add_argument("--policy", type=Path, required=True)
    plan.add_argument("--request", type=Path, required=True)
    plan.add_argument("--backend-evidence", type=Path, required=True)
    plan.set_defaults(handler=command_plan)

    effective = subcommands.add_parser("verify-effective")
    effective.add_argument("--policy", type=Path, required=True)
    effective.add_argument("--request", type=Path, required=True)
    effective.add_argument("--effective", type=Path, required=True)
    effective.set_defaults(handler=command_verify_effective)

    execute = subcommands.add_parser("execute-plan")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--timeout-seconds", type=float, required=True)
    execute.add_argument("--output-limit-bytes", type=int, required=True)
    execute.add_argument(
        "--test-only-confirm-no-security-certification",
        action="store_true",
    )
    execute.set_defaults(handler=command_execute_plan)

    bundle = subcommands.add_parser("verify-bundle")
    bundle.add_argument("--bundle", type=Path, required=True)
    bundle.set_defaults(handler=command_verify_bundle)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _write_json({"status": "BLOCKED", "error_code": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
