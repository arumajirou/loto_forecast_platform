from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_audit" / "taj20_publish_evidence_v2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("taj20_publish_evidence_v2", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_identity_publication_matches_actual_planner_contract(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    for name in module.IDENTITY_PUBLICATION_FILES:
        (source / name).write_text(f"{name}\n", encoding="utf-8")

    assert "ARTIFACT_MANIFEST.json" not in module.IDENTITY_PUBLICATION_FILES
    module._copy_identity_plan(source, destination)
    assert sorted(path.name for path in destination.iterdir()) == sorted(
        module.IDENTITY_PUBLICATION_FILES
    )


def test_secret_marker_is_rejected_before_publication(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "evidence.json").write_text(
        '{"token":"github_pat_example"}\n', encoding="utf-8"
    )

    with pytest.raises(module.PublishError, match="secret-like marker rejected"):
        module._assert_no_secret_markers(tmp_path)


def test_stale_local_branch_at_main_is_removed(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    branch = "evidence/taj20-runtime-test"
    subprocess.run(["git", "-C", str(repo), "branch", branch, head], check=True)

    assert module._remove_stale_local_branch(repo, branch, head) is True
    probe = subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", f"refs/heads/{branch}"],
        check=False,
    )
    assert probe.returncode != 0


def test_stale_local_branch_with_unique_commit_is_preserved(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
    main_head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    branch = "evidence/taj20-runtime-test"
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", branch], check=True)
    (repo / "unique.txt").write_text("unique\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "unique.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "unique"], check=True)
    subprocess.run(["git", "-C", str(repo), "switch", "-q", "main"], check=True)

    with pytest.raises(module.PublishError, match="contains unique commits"):
        module._remove_stale_local_branch(repo, branch, main_head)
