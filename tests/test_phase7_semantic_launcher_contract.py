from __future__ import annotations

from pathlib import Path


LAUNCHER = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "phase7_semantic_diagnosis"
    / "run_semantic_diagnosis.ps1"
)


def source() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_publish_does_not_require_clean_primary_worktree() -> None:
    text = source()
    assert "PublishEvidence requires a clean working tree" not in text
    assert "git status --porcelain" not in text


def test_publish_does_not_switch_or_stage_primary_worktree() -> None:
    text = source()
    forbidden = (
        "git -C $Repo switch",
        "git -C $Repo add",
        "git -C $Repo commit",
        "git -C $Repo push",
    )
    for fragment in forbidden:
        assert fragment not in text


def test_publish_uses_server_side_git_data_api() -> None:
    text = source()
    required = (
        'repos/$RepositoryName/git/blobs',
        'repos/$RepositoryName/git/trees',
        'repos/$RepositoryName/git/commits',
        'repos/$RepositoryName/git/refs',
        "Invoke-GhJson",
    )
    for fragment in required:
        assert fragment in text


def test_diagnosis_output_defaults_outside_repository() -> None:
    text = source()
    assert '$OutputRoot = Join-Path $HOME "Downloads"' in text
    assert '$Out = Join-Path $Repo "evidence\\phase7_semantic_diagnosis\\$RunId"' not in text


def test_remote_evidence_path_is_narrow_and_run_scoped() -> None:
    text = source()
    assert '"evidence/phase7_semantic_diagnosis/$RunIdentifier/$Relative"' in text
    assert '"evidence/phase7-semantic-diagnosis-$RunId"' in text


def test_launcher_reports_no_primary_worktree_mutation() -> None:
    text = source()
    assert 'Write-Host "PRIMARY_WORKTREE_MUTATED=NO"' in text
