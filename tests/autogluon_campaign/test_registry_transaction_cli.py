from __future__ import annotations

import json
from pathlib import Path

from loto.autogluon_campaign import registry_transaction_cli as cli
from loto.autogluon_campaign.registry_transaction import create_registry_transaction
from tests.autogluon_campaign.p18_test_support import always_verify
from tests.autogluon_campaign.p19_test_support import (
    make_p18_bundle,
    make_registry,
    make_request,
    registry_target,
)


def test_cli_bootstrap_and_state(tmp_path: Path, capsys) -> None:
    path = tmp_path / "registry" / "state.json"
    path.parent.mkdir()
    assert cli.main(
        [
            "bootstrap",
            "--registry",
            str(path),
            "--registry-target",
            registry_target(path),
        ]
    ) == 0
    capsys.readouterr()
    assert cli.main(["state", "--registry", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["generation"] == 0
    assert payload["backend"] == "file-json-cas-v1"


def test_cli_transact_and_verify_route_exact_arguments(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    registry, _, initial_sha = make_registry(tmp_path)
    p18 = make_p18_bundle(tmp_path, registry)
    request = make_request(initial_sha)
    output = tmp_path / "cli-output"

    def injected(**kwargs):
        return create_registry_transaction(
            **kwargs,
            signature_verifier=always_verify,
        )

    monkeypatch.setattr(cli, "create_registry_transaction", injected)
    assert cli.main(
        [
            "transact",
            "--p18",
            str(p18),
            "--registry",
            str(registry),
            "--output",
            str(output),
            "--run-id",
            request.run_id,
            "--git-commit",
            request.git_commit,
            "--expected-state-sha256",
            request.expected_current_state_sha256,
            "--transaction-nonce",
            request.transaction_nonce,
            "--executed-at-utc",
            request.executed_at_utc,
        ]
    ) == 0
    transaction = json.loads(capsys.readouterr().out)
    assert transaction["decision"] == "REGISTRY_TRANSACTION_COMMITTED"
    assert cli.main(["verify", "--run", str(output)]) == 0
    verification = json.loads(capsys.readouterr().out)
    assert verification["status"] == "PASS"


def test_cli_returns_exit_two_for_invalid_state(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.json"
    assert cli.main(["state", "--registry", str(missing)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAILED"
