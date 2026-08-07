from loto.statsforecast import runtime_lane_remediation_hardening as hardening


def test_default_injects_hardened_end_to_end(monkeypatch) -> None:
    captured = {}

    def base(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(hardening, "_execute_bounded_remediation", base)
    result = hardening.execute_bounded_remediation("repo", "triage", "out")

    assert result == "result"
    assert captured["end_to_end_runner"] is hardening.run_end_to_end_certification


def test_explicit_end_to_end_override_is_preserved(monkeypatch) -> None:
    captured = {}
    custom_runner = lambda *_args, **_kwargs: None

    def base(*_args, **kwargs):
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(hardening, "_execute_bounded_remediation", base)
    hardening.execute_bounded_remediation(
        "repo",
        "triage",
        "out",
        end_to_end_runner=custom_runner,
    )

    assert captured["end_to_end_runner"] is custom_runner
