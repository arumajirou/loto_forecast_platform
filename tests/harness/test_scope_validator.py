import subprocess
import sys
from pathlib import Path


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=path, check=True)


def validator() -> Path:
    return Path(__file__).parents[2] / "scripts/harness/validate_scope.py"


def test_scope_validator_allows_harness_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    path = tmp_path / "src/loto/harness/new.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(validator()), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HARNESS_SCOPE=VERIFIED" in result.stdout


def test_scope_validator_blocks_forecast_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    path = tmp_path / "src/loto/forecast.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(validator()), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 20
    assert "BLOCKED\tsrc/loto/forecast.py" in result.stdout


def test_scope_validator_allows_uv_lock(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(validator()), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALLOWED\tuv.lock" in result.stdout
