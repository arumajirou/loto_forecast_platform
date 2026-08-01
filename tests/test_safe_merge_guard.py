from pathlib import Path

SCRIPT = Path("scripts/safe_merge_pr.sh")


def test_safe_merge_script_exists() -> None:
    assert SCRIPT.is_file()


def test_safe_merge_requires_successful_checks() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'select(.name == "test")' in text
    assert '.status != "COMPLETED"' in text
    assert '.conclusion != "SUCCESS"' in text


def test_safe_merge_uses_squash_and_delete_branch() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'gh pr merge "${PR_NUMBER}"' in text
    assert "--squash" in text
    assert "--delete-branch" in text
