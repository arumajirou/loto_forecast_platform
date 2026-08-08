from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from loto.sktime_campaign.approval_authorization import (
    RegistryTransactionRequest,
    verify_registry_authorization,
)
from loto.sktime_campaign.registry_transaction import (
    FileRegistryState,
    P8RegistryTransactionRequest,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_sha256sums(directory: Path) -> None:
    seen: set[str] = set()
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        if name in seen or file_sha256(directory / name) != expected:
            raise ValueError(f"P7 SHA256SUMS mismatch: {name}")
        seen.add(name)
    expected = {
        path.name for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    }
    if seen != expected:
        raise ValueError("P7 SHA256SUMS coverage mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p7-dir", type=Path, required=True)
    parser.add_argument("--registry-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--code-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--requested-at-utc", required=True)
    parser.add_argument("--transaction-nonce", required=True)
    args = parser.parse_args()

    p7_dir = args.p7_dir.resolve()
    verify_sha256sums(p7_dir)
    response = load_json(p7_dir / "response.json")
    if response.get("decision") != "AUTHORIZED_FOR_ONE_REGISTRY_TRANSACTION":
        raise ValueError("P7 did not authorize a registry transaction")
    if response.get("registry_write_authorized") is not True:
        raise ValueError("P7 registry authorization is disabled")
    if response.get("registry_write_executed") is not False:
        raise ValueError("P7 already claims a registry write")
    authorization = load_json(p7_dir / "REGISTRY_AUTHORIZATION.json")
    verify_registry_authorization(authorization)
    requirements = load_json(p7_dir / "REGISTRY_TRANSACTION_REQUIREMENTS.json")
    if requirements.get("authorization_id") != authorization["authorization_id"]:
        raise ValueError("P7 transaction requirements changed authorization ID")
    if requirements.get("authorization_seal_sha256") != authorization["seal_sha256"]:
        raise ValueError("P7 transaction requirements changed authorization seal")
    if requirements.get("subject") != authorization["subject"]:
        raise ValueError("P7 transaction requirements changed registry subject")

    registry_state = FileRegistryState.model_validate(load_json(args.registry_state.resolve()))
    transaction = RegistryTransactionRequest(
        authorization_id=authorization["authorization_id"],
        authorization_seal_sha256=authorization["seal_sha256"],
        transaction_nonce=args.transaction_nonce,
        requested_at_utc=args.requested_at_utc,
        expected_registry_state_sha256=registry_state.state_sha256,
        subject=authorization["subject"],
    )
    request = P8RegistryTransactionRequest(
        output_dir=str(args.evidence_output_dir.resolve()),
        run_id=args.run_id,
        git_commit=args.git_commit,
        code_sha256=args.code_sha256,
        config_sha256=args.config_sha256,
        p7_bundle_sha256=file_sha256(p7_dir / "SHA256SUMS"),
        registry_state_path=str(args.registry_state.resolve()),
        authorization=authorization,
        transaction=transaction,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
