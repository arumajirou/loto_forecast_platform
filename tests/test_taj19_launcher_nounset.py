from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "taj19.sh"


def test_taj19_launcher_does_not_expand_same_statement_locals_under_nounset() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert 'local root="$1" plan_root="$root/preflight-plan"' not in text
    assert 'local root="$1" resume_flag="${2:-}" campaign="$root/campaign"' not in text
    assert 'local root="$1" campaign="$root/campaign"' not in text


def test_taj19_launcher_assigns_dependent_locals_after_root() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert 'local root="$1"\n    local plan_root="$root/preflight-plan"' in text
    assert 'local root="$1"\n    local resume_flag="${2:-}"\n    local campaign="$root/campaign"' in text
    assert 'local root="$1"\n    local campaign="$root/campaign"' in text
