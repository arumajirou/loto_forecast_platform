from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "taj20.sh"


def test_verify_runtime_does_not_mutate_runtime_evidence() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    start = text.index("verify_runtime() {")
    end = text.index("\n}\n\ncase", start)
    verify_block = text[start:end]

    assert '"${PY_CMD[@]}" "$RUNNER" verify' not in verify_block
    assert '"${PY_CMD[@]}" "$ACCEPTANCE"' in verify_block
    assert "Reverification must be read-only" in verify_block
