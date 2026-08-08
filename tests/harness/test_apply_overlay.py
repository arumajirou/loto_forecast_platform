import subprocess
import sys
from pathlib import Path


def base_pyproject() -> str:
    return """[project]
name = "loto-forecast-platform"
[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2", "sqlalchemy>=2.0"]
[project.scripts]
loto-integrity = "loto.verify.integrity:main"
"""


def make_overlay(root: Path) -> Path:
    overlay = root / "overlay"
    harness = overlay / "src/loto/harness"
    harness.mkdir(parents=True)
    (harness / "cli.py").write_text("def main(): return 0\n", encoding="utf-8")
    (overlay / "CLAUDE.harness.md").write_text("# Harness rules\n", encoding="utf-8")
    return overlay


def installer_path() -> Path:
    return Path(__file__).parents[2] / "scripts/harness/apply_overlay.py"


def test_overlay_application_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    (target / "pyproject.toml").write_text(base_pyproject(), encoding="utf-8")
    (target / "CLAUDE.md").write_text("# Existing rules\n", encoding="utf-8")
    overlay = make_overlay(tmp_path)
    script = installer_path()

    for _ in range(2):
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                str(target),
                "--overlay",
                str(overlay),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    text = (target / "pyproject.toml").read_text(encoding="utf-8")
    assert text.count("\nharness = [\n") == 1
    assert text.count('loto-harness = "loto.harness.cli:main"') == 1
    assert (target / "src/loto/harness/cli.py").is_file()
    assert (target / "CLAUDE.harness.md").is_file()
    claude_text = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude_text.startswith("# Existing rules")
    assert claude_text.count("@CLAUDE.harness.md") == 1


def test_overlay_rejects_wrong_project(tmp_path: Path) -> None:
    target = tmp_path / "wrong"
    target.mkdir()
    wrong_project = base_pyproject().replace("loto-forecast-platform", "other")
    (target / "pyproject.toml").write_text(wrong_project, encoding="utf-8")
    overlay = make_overlay(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(installer_path()),
            str(target),
            "--overlay",
            str(overlay),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "not loto-forecast-platform" in result.stderr
