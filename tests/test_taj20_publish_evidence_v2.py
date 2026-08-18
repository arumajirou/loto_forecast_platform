from __future__ import annotations

import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "runtime_audit" / "taj20_publish_evidence_v2.py"
LAUNCHER_PATH = ROOT / "tools" / "taj20-publish-evidence-v2.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("taj20_publish_evidence_v2", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def init_repo(repo: Path) -> str:
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-q", "-m", "base")
    return git_head(repo)


def write_checksum_contract(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True)
    lines: list[str] = []
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_checksum_contract_copies_identity_without_manifest(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "identity"
    destination = tmp_path / "copied"
    files = {
        "IDENTITY_SUMMARY.json": "{}\n",
        "UNIFIED_CATALOG.json": "[]\n",
        "PROBABILISTIC_NATIVE.json": "[]\n",
        "EXECUTION_SURFACES.json": "{}\n",
    }
    write_checksum_contract(source, files)

    copied = module._copy_checksum_contract(source, destination)

    assert set(copied) == set(files)
    assert not (destination / "ARTIFACT_MANIFEST.json").exists()
    module.base._verify_sha256s(destination)


def test_checksum_contract_copies_actual_preflight_without_manifest(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "preflight"
    destination = tmp_path / "copied"
    files = {
        "UNIFIED_IDENTITY_MANIFEST.json": "{}\n",
        "IDENTITY_BACKEND_MAPPING.json": "{}\n",
        "INCREMENTAL_MATRIX_PLAN.json": "{}\n",
        "REUSE_PROVENANCE.json": "{}\n",
        "PRECHECK_SUMMARY.json": "{}\n",
    }
    write_checksum_contract(source, files)

    copied = module._copy_checksum_contract(source, destination)

    assert set(copied) == set(files)
    assert not (destination / "ARTIFACT_MANIFEST.json").exists()
    module.base._verify_sha256s(destination)


def test_checksum_contract_preserves_nested_paths(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    destination = tmp_path / "copied"
    write_checksum_contract(source, {"nested/evidence.json": "{}\n"})

    module._copy_checksum_contract(source, destination)

    assert (destination / "nested" / "evidence.json").read_text(encoding="utf-8") == "{}\n"
    module.base._verify_sha256s(destination)


def test_checksum_contract_rejects_path_escape(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (source / "SHA256SUMS").write_text(
        f"{digest}  ../outside.json\n",
        encoding="utf-8",
    )

    with pytest.raises(module.PublishError, match="escapes root"):
        module._copy_checksum_contract(source, tmp_path / "copied")


def test_secret_marker_is_rejected_before_publication(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "evidence.json").write_text(
        '{"token":"github_pat_example"}\n',
        encoding="utf-8",
    )

    with pytest.raises(module.PublishError, match="secret-like marker rejected"):
        module._assert_no_secret_markers(tmp_path)


def test_stale_local_branch_at_main_is_removed(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    head = init_repo(repo)
    branch = "evidence/taj20-runtime-test"
    git(repo, "branch", branch, head)

    assert module._remove_stale_local_branch(repo, branch, head) is True
    probe = git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
    assert probe.returncode != 0


def test_stale_local_branch_with_unique_commit_is_preserved(tmp_path: Path) -> None:
    module = load_module()
    repo = tmp_path / "repo"
    main_head = init_repo(repo)
    branch = "evidence/taj20-runtime-test"
    git(repo, "switch", "-q", "-c", branch)
    (repo / "unique.txt").write_text("unique\n", encoding="utf-8")
    git(repo, "add", "unique.txt")
    git(repo, "commit", "-q", "-m", "unique")
    git(repo, "switch", "-q", "main")

    with pytest.raises(module.PublishError, match="contains unique commits"):
        module._remove_stale_local_branch(repo, branch, main_head)


def test_launcher_recovers_branch_that_is_ancestor_of_advanced_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    old_main = init_repo(repo)
    branch = "evidence/taj20-runtime-test"
    git(repo, "branch", branch, old_main)

    (repo / "file.txt").write_text("advanced\n", encoding="utf-8")
    git(repo, "add", "file.txt")
    git(repo, "commit", "-q", "-m", "advance main")
    new_main = git_head(repo)

    ancestor = git(repo, "merge-base", "--is-ancestor", old_main, new_main, check=False)
    assert ancestor.returncode == 0

    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert 'merge-base --is-ancestor "$BRANCH_TIP" "$MAIN_TIP"' in launcher
    assert 'branch -D "$BRANCH"' in launcher
