from loto.statsforecast import runtime_lane
from loto.statsforecast import runtime_lane_end_to_end_hardening as hardening


def test_default_injects_hardened_admission(monkeypatch, tmp_path) -> None:
    captured = {}

    def base(repo_root, output_root, **kwargs):
        captured["repo_root"] = repo_root
        captured["output_root"] = output_root
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(hardening, "_run_end_to_end_certification", base)
    result = hardening.run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        expected_commit="a" * 40,
    )

    assert result == "result"
    assert captured["admission_inspector"] is hardening.inspect_target_host_archive
    assert captured["admission_writer"] is hardening.write_admission_artifacts


def test_explicit_admission_overrides_are_preserved(monkeypatch, tmp_path) -> None:
    captured = {}

    def custom_inspector(*_args, **_kwargs):
        return {}

    def custom_writer(*_args, **_kwargs):
        return {}

    def base(_repo_root, _output_root, **kwargs):
        captured.update(kwargs)
        return "result"

    monkeypatch.setattr(hardening, "_run_end_to_end_certification", base)
    hardening.run_end_to_end_certification(
        tmp_path,
        tmp_path / "out",
        admission_inspector=custom_inspector,
        admission_writer=custom_writer,
    )

    assert captured["admission_inspector"] is custom_inspector
    assert captured["admission_writer"] is custom_writer


def test_public_runtime_lane_exports_hardened_wrapper() -> None:
    assert runtime_lane.run_end_to_end_certification is hardening.run_end_to_end_certification
