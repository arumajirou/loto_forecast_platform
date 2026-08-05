from pathlib import Path

import pytest

from loto.harness.errors import UnsafeOperation
from loto.harness.security import ensure_allowed_path, redact_text


def test_redacts_common_secret_assignment() -> None:
    value = redact_text("API_KEY=abcdef TOKEN: qwerty ordinary=value")
    assert "abcdef" not in value
    assert "qwerty" not in value
    assert "ordinary=value" in value


def test_path_allowlist(tmp_path: Path) -> None:
    inside = tmp_path / "repo" / "file.txt"
    inside.parent.mkdir()
    assert ensure_allowed_path(inside, [tmp_path]) == inside.resolve()
    with pytest.raises(UnsafeOperation):
        ensure_allowed_path("/etc/passwd", [tmp_path])
