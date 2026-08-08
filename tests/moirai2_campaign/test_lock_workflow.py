from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from loto.moirai2_campaign.lock_review import (
    REPORT_FILENAME,
    inspect_lock,
    sha256_file,
    validate_installed_review,
)
from tests.moirai2_campaign.test_lock_review import LOCK, PYPROJECT


def _load_script(name: str) -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(tmp_path: Path, lock: str = LOCK) -> Path:
    candidate = tmp_path / "candidate"
    project = candidate / "candidate-project"
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text(PYPROJECT + "\n", encoding="utf-8")
    (project / "uv.lock").write_text(lock + "\n", encoding="utf-8")
    report = inspect_lock(
        pyproject_path=project / "pyproject.toml",
        lock_path=project / "uv.lock",
        runtime_lane="supported-py311",
    )
    (candidate / REPORT_FILENAME).write_text(
        json.dumps(report, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidate


def _environment(tmp_path: Path) -> Path:
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "pyproject.toml").write_text(PYPROJECT + "\n", encoding="utf-8")
    return environment


def _install_output(tmp_path: Path, name: str = "install-output") -> Path:
    output = tmp_path / name
    output.mkdir()
    return output


def test_installer_dry_run_does_not_modify_lane(tmp_path: Path) -> None:
    module = _load_script("install_reviewed_moirai2_lock.py")
    candidate = _candidate(tmp_path)
    environment = _environment(tmp_path)
    module.RUNTIME_LANES = {"supported-py311": environment}
    lock_sha = sha256_file(candidate / "candidate-project" / "uv.lock")
    result = module.install_candidate(
        candidate_dir=candidate,
        output_dir=_install_output(tmp_path),
        runtime_lane="supported-py311",
        reviewer="human-reviewer",
        reviewed_at="2026-08-06T00:00:00+09:00",
        expected_lock_sha256=lock_sha,
        approval_token=module.APPROVAL_TOKEN,
        apply=False,
        replace_existing_sha256=None,
    )
    assert result["status"] == "READY"
    assert not (environment / "uv.lock").exists()


def test_installer_applies_three_cross_hashed_artifacts(tmp_path: Path) -> None:
    module = _load_script("install_reviewed_moirai2_lock.py")
    candidate = _candidate(tmp_path)
    environment = _environment(tmp_path)
    module.RUNTIME_LANES = {"supported-py311": environment}
    lock_sha = sha256_file(candidate / "candidate-project" / "uv.lock")
    candidate_manifest_before = {
        path.relative_to(candidate).as_posix(): sha256_file(path)
        for path in candidate.rglob("*")
        if path.is_file()
    }
    result = module.install_candidate(
        candidate_dir=candidate,
        output_dir=_install_output(tmp_path),
        runtime_lane="supported-py311",
        reviewer="human-reviewer",
        reviewed_at="2026-08-06T00:00:00+09:00",
        expected_lock_sha256=lock_sha,
        approval_token=module.APPROVAL_TOKEN,
        apply=True,
        replace_existing_sha256=None,
    )
    assert result["status"] == "INSTALLED"
    evidence = validate_installed_review(
        environment_path=environment,
        runtime_lane="supported-py311",
    )
    assert evidence["reviewer"] == "human-reviewer"
    assert (environment / "LOCK_REVIEW_REPORT.json").is_file()
    assert (environment / "LOCK_REVIEW_APPROVAL.json").is_file()
    candidate_manifest_after = {
        path.relative_to(candidate).as_posix(): sha256_file(path)
        for path in candidate.rglob("*")
        if path.is_file()
    }
    assert candidate_manifest_after == candidate_manifest_before


def test_installer_rejects_wrong_candidate_hash(tmp_path: Path) -> None:
    module = _load_script("install_reviewed_moirai2_lock.py")
    candidate = _candidate(tmp_path)
    environment = _environment(tmp_path)
    module.RUNTIME_LANES = {"supported-py311": environment}
    with pytest.raises(ValueError, match="candidate lock SHA"):
        module.install_candidate(
            candidate_dir=candidate,
            output_dir=_install_output(tmp_path),
            runtime_lane="supported-py311",
            reviewer="human-reviewer",
            reviewed_at="2026-08-06T00:00:00+09:00",
            expected_lock_sha256="0" * 64,
            approval_token=module.APPROVAL_TOKEN,
            apply=True,
            replace_existing_sha256=None,
        )


def test_installer_rejects_unapproved_token(tmp_path: Path) -> None:
    module = _load_script("install_reviewed_moirai2_lock.py")
    candidate = _candidate(tmp_path)
    environment = _environment(tmp_path)
    module.RUNTIME_LANES = {"supported-py311": environment}
    lock_sha = sha256_file(candidate / "candidate-project" / "uv.lock")
    with pytest.raises(PermissionError, match="approval token"):
        module.install_candidate(
            candidate_dir=candidate,
            output_dir=_install_output(tmp_path),
            runtime_lane="supported-py311",
            reviewer="human-reviewer",
            reviewed_at="2026-08-06T00:00:00+09:00",
            expected_lock_sha256=lock_sha,
            approval_token="WRONG",
            apply=True,
            replace_existing_sha256=None,
        )


def test_installer_requires_replacement_guard(tmp_path: Path) -> None:
    module = _load_script("install_reviewed_moirai2_lock.py")
    candidate = _candidate(tmp_path)
    environment = _environment(tmp_path)
    (environment / "uv.lock").write_text("existing\n", encoding="utf-8")
    module.RUNTIME_LANES = {"supported-py311": environment}
    lock_sha = sha256_file(candidate / "candidate-project" / "uv.lock")
    with pytest.raises(FileExistsError, match="replace-existing-sha256"):
        module.install_candidate(
            candidate_dir=candidate,
            output_dir=_install_output(tmp_path),
            runtime_lane="supported-py311",
            reviewer="human-reviewer",
            reviewed_at="2026-08-06T00:00:00+09:00",
            expected_lock_sha256=lock_sha,
            approval_token=module.APPROVAL_TOKEN,
            apply=True,
            replace_existing_sha256=None,
        )


def test_candidate_builder_is_non_destructive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script("generate_moirai2_lock_candidate.py")
    environment = _environment(tmp_path)
    output = tmp_path / "output"
    module.RUNTIME_LANES = {"supported-py311": environment}
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/uv")

    class Result:
        returncode = 0
        stdout = "resolved"
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        project = Path(command[command.index("--project") + 1])
        (project / "uv.lock").write_text(LOCK + "\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.build_candidate(
        runtime_lane="supported-py311",
        output_dir=output,
        python_spec="3.11",
        timeout_seconds=60,
    )
    assert result["status"] == "PASS"
    assert result["lane_modified"] is False
    assert not (environment / "uv.lock").exists()
    assert (output / REPORT_FILENAME).is_file()
    assert (output / "LOCK_DEPENDENCY_INVENTORY.csv").is_file()


def test_candidate_builder_retains_failed_static_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script("generate_moirai2_lock_candidate.py")
    environment = _environment(tmp_path)
    output = tmp_path / "output"
    module.RUNTIME_LANES = {"supported-py311": environment}
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/uv")
    changed = LOCK.replace(
        'source = { registry = "https://pypi.org/simple" }',
        'source = { git = "https://example.invalid/repo.git" }',
        1,
    )

    class Result:
        returncode = 0
        stdout = "resolved"
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Result:
        project = Path(command[command.index("--project") + 1])
        (project / "uv.lock").write_text(changed + "\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.build_candidate(
        runtime_lane="supported-py311",
        output_dir=output,
        python_spec=None,
        timeout_seconds=60,
    )
    assert result["status"] == "FAILED"
    report = json.loads((output / REPORT_FILENAME).read_text(encoding="utf-8"))
    assert report["violations"]
