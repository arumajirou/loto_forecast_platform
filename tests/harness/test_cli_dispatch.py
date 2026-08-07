from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from loto.harness import cli


class _FakeSettings:
    @staticmethod
    def from_yaml(_path: Path) -> object:
        return object()


def test_profile_ab_main_does_not_read_certify_only_profile_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_profile_ab(
        settings: object,
        model_key: str,
        *,
        modes: list[str],
        repetitions: int,
        context_tokens: int,
        context_utilization: float,
        seed: int,
        output: str | None,
    ) -> int:
        captured.update(
            {
                "settings": settings,
                "model_key": model_key,
                "modes": modes,
                "repetitions": repetitions,
                "context_tokens": context_tokens,
                "context_utilization": context_utilization,
                "seed": seed,
                "output": output,
            }
        )
        return 0

    monkeypatch.setattr(cli, "HarnessSettings", _FakeSettings)
    monkeypatch.setattr(cli, "_profile_ab", fake_profile_ab)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-harness",
            "profile-ab",
            "qwen3-test",
            "--modes",
            "generic,quality",
            "--repetitions",
            "5",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    assert captured["model_key"] == "qwen3-test"
    assert captured["modes"] == ["generic", "quality"]
    assert captured["repetitions"] == 5
    assert captured["seed"] == 1


def test_certify_main_forwards_profile_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_certify(
        settings: object,
        model_key: str,
        *,
        contexts: list[int] | None,
        deep_context: bool,
        context_utilization: float,
        context_repetitions: int,
        output: str | None,
        profile_mode: str,
    ) -> int:
        captured.update(
            {
                "settings": settings,
                "model_key": model_key,
                "contexts": contexts,
                "deep_context": deep_context,
                "context_utilization": context_utilization,
                "context_repetitions": context_repetitions,
                "output": output,
                "profile_mode": profile_mode,
            }
        )
        return 0

    monkeypatch.setattr(cli, "HarnessSettings", _FakeSettings)
    monkeypatch.setattr(cli, "_certify", fake_certify)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loto-harness",
            "certify",
            "qwen3-test",
            "--contexts",
            "8192,16384",
            "--profile-mode",
            "quality",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    assert captured["contexts"] == [8192, 16384]
    assert captured["profile_mode"] == "quality"


def test_json_report_manifest_uses_absolute_path(tmp_path: Path) -> None:
    report = cli._write_json_report(
        tmp_path / "report.json",
        {"status": "VERIFIED"},
    )
    manifest = report.with_suffix(".json.sha256")
    manifest_text = manifest.read_text(encoding="utf-8").strip()
    digest, manifest_path = manifest_text.split("  ", 1)

    assert report.is_absolute()
    assert manifest_path == str(report)
    assert digest == hashlib.sha256(report.read_bytes()).hexdigest()
