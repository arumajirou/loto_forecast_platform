from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from loto.autogluon_campaign.approval_authorization_contract import (
    ApprovalAuthorizationError,
)
from loto.autogluon_campaign.registry_transaction import (
    create_registry_transaction,
    verify_registry_transaction,
)
from loto.autogluon_campaign.registry_transaction_contract import (
    RegistryPolicy,
    RegistryTransactionRequest,
)
from loto.autogluon_campaign.registry_transaction_io import (
    bootstrap_registry,
    load_registry_state,
)


def _print(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _load_policy(path: Path | None) -> RegistryPolicy:
    if path is None:
        return RegistryPolicy()
    return RegistryPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _bootstrap(args: argparse.Namespace) -> int:
    state = bootstrap_registry(
        registry_path=args.registry,
        registry_target=args.registry_target,
    )
    _print(state.model_dump(mode="json"))
    return 0


def _state(args: argparse.Namespace) -> int:
    _print(load_registry_state(args.registry).model_dump(mode="json"))
    return 0


def _transact(args: argparse.Namespace) -> int:
    request = RegistryTransactionRequest(
        run_id=args.run_id,
        git_commit=args.git_commit,
        expected_current_state_sha256=args.expected_state_sha256,
        transaction_nonce=args.transaction_nonce,
        executed_at_utc=args.executed_at_utc,
        policy=_load_policy(args.policy),
    )
    result = create_registry_transaction(
        p18_evidence_dir=args.p18,
        registry_path=args.registry,
        output_dir=args.output,
        request=request,
    )
    _print(result.model_dump(mode="json"))
    return 0


def _verify(args: argparse.Namespace) -> int:
    _print(verify_registry_transaction(args.run))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AutoGluon P19 file-json compare-and-swap registry"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap.add_argument("--registry", type=Path, required=True)
    bootstrap.add_argument("--registry-target", required=True)
    bootstrap.set_defaults(handler=_bootstrap)

    state = subparsers.add_parser("state")
    state.add_argument("--registry", type=Path, required=True)
    state.set_defaults(handler=_state)

    transact = subparsers.add_parser("transact")
    transact.add_argument("--p18", type=Path, required=True)
    transact.add_argument("--registry", type=Path, required=True)
    transact.add_argument("--output", type=Path, required=True)
    transact.add_argument("--run-id", required=True)
    transact.add_argument("--git-commit", required=True)
    transact.add_argument("--expected-state-sha256", required=True)
    transact.add_argument("--transaction-nonce", required=True)
    transact.add_argument("--executed-at-utc", required=True)
    transact.add_argument("--policy", type=Path)
    transact.set_defaults(handler=_transact)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--run", type=Path, required=True)
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ApprovalAuthorizationError, ValueError, OSError, KeyError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        _print({"status": "FAILED", "error_code": code, "message": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
