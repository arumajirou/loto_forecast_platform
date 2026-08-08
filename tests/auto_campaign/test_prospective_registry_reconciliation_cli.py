from __future__ import annotations

from pathlib import Path

from loto.auto_campaign import cli


def test_reconcile_command_routes_without_campaign_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    receipt = tmp_path / "receipt"
    output = tmp_path / "reconciliation"
    captured = {}

    def reconcile(**kwargs):
        captured.update(kwargs)
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "reconcile_prospective_registry", reconcile)
    args = cli.build_parser().parse_args(
        [
            "reconcile-scoring-registry",
            "--run",
            str(receipt),
            "--output",
            str(output),
            "--float-tolerance",
            "1e-10",
        ]
    )

    result = cli._run_portable_command(args, tmp_path)

    assert result == {"status": "PASS"}
    assert captured["receipt_root"] == receipt.resolve()
    assert captured["output"] == output.resolve()
    assert captured["options"].float_tolerance == 1e-10
    assert captured["options"].require_remote_artifacts is True


def test_reconcile_diagnostic_skip_is_explicit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {}
    monkeypatch.setattr(
        cli,
        "reconcile_prospective_registry",
        lambda **kwargs: captured.update(kwargs) or {"status": "PASS"},
    )
    args = cli.build_parser().parse_args(
        [
            "reconcile-scoring-registry",
            "--run",
            "receipt",
            "--output",
            "reconciliation",
            "--skip-remote-artifact-check",
        ]
    )

    cli._run_portable_command(args, tmp_path)

    assert captured["options"].require_remote_artifacts is False


def test_verify_reconciliation_command_is_configless(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected = {"status": "PASS", "operational_status": "DRIFT"}
    monkeypatch.setattr(
        cli,
        "verify_registry_reconciliation",
        lambda root: expected | {"root": str(root)},
    )
    args = cli.build_parser().parse_args(["verify-registry-reconciliation", "--run", "artifact"])

    result = cli._run_portable_command(args, tmp_path)

    assert result == expected | {"root": str((tmp_path / "artifact").resolve())}


def test_reconcile_failure_is_structured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "reconcile_prospective_registry",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid receipt")),
    )
    args = cli.build_parser().parse_args(
        [
            "reconcile-scoring-registry",
            "--run",
            "receipt",
            "--output",
            "output",
        ]
    )

    result = cli._run_portable_command(args, tmp_path)

    assert result == {
        "status": "FAIL",
        "command": "reconcile-scoring-registry",
        "error_type": "ValueError",
        "error": "invalid receipt",
    }
