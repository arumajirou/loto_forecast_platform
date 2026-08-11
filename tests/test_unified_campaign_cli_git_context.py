from __future__ import annotations

from types import SimpleNamespace

from loto.evaluation import unified_campaign_cli


def test_git_commit_resolves_from_repository_root(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["cwd"] = kwargs.get("cwd")
        observed["check"] = kwargs.get("check")
        return SimpleNamespace(stdout="abc123\n")

    monkeypatch.setattr(unified_campaign_cli.subprocess, "run", fake_run)

    assert unified_campaign_cli._git_commit() == "abc123"
    assert observed["command"] == ["git", "rev-parse", "HEAD"]
    assert observed["cwd"] == unified_campaign_cli.REPO_ROOT
    assert observed["check"] is True
