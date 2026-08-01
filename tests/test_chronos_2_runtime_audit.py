from __future__ import annotations

import json
from pathlib import Path

from loto.models.catalog import get_model_spec
from loto.models.providers.registry import get_foundation_provider

ROOT = Path(__file__).resolve().parents[1]

MODEL_ID = "chronos-2"
REPO_ID = "amazon/chronos-2"
REVISION = "29ec3766d36d6f73f0696f85560a422f50e8498c"

WEIGHT_SHA256 = "ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42"
CONFIG_SHA256 = "ef1143bfdc9c0376d9a056eefca46cb4b1ec3d0ffacd541ff56feb40fb708031"

EVIDENCE_DIR = ROOT / "audit" / "tsfm-runtime" / MODEL_ID
STATUS_PATH = ROOT / "audit" / "tsfm-runtime" / "runtime-status.json"
RUNNER_PATH = ROOT / "scripts" / "run_chronos_2_provider.py"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_chronos_2_catalog_and_registry() -> None:
    spec = get_model_spec(MODEL_ID)

    assert spec.model_id == MODEL_ID
    assert spec.library == "chronos"
    assert spec.class_name == "Chronos2Pipeline"

    assert spec.default_params["model_name"] == REPO_ID
    assert spec.default_params["revision"] == REVISION
    assert spec.default_params["batch_size"] == 256
    assert spec.default_params["context_length"] == 512
    assert spec.default_params["cross_learning"] is False

    provider_class = get_foundation_provider(spec)

    assert provider_class.__name__ == "ChronosProvider"


def test_chronos_2_runner_is_present_and_pinned() -> None:
    assert RUNNER_PATH.is_file()

    source = RUNNER_PATH.read_text(encoding="utf-8")

    required_fragments = [
        f'MODEL_ID = "{MODEL_ID}"',
        f'REPO_ID = "{REPO_ID}"',
        f'REVISION = "{REVISION}"',
        WEIGHT_SHA256,
        CONFIG_SHA256,
        "local_files_only=True",
        'device_map="cuda"',
        "cpu_fallback",
        "peak_vram_bytes",
    ]

    for fragment in required_fragments:
        assert fragment in source


def test_chronos_2_runtime_result() -> None:
    result = _load_json(EVIDENCE_DIR / "runtime-result.json")

    assert result["status"] == "PASS"
    assert result["model_id"] == MODEL_ID
    assert result["repo_id"] == REPO_ID
    assert result["revision"] == REVISION
    assert result["runtime_vram_certified"] is True

    assert result["device"] == "cuda:0"
    assert result["model_device"] == "cuda:0"
    assert result["input_devices"] == ["cpu"] * 7

    assert result["cpu_preprocessing"] is True
    assert result["cpu_fallback"] is False
    assert result["peak_vram_bytes"] > 0
    assert result["gpu_pid"] > 0

    assert result["prediction_shape"] == [7]
    assert result["quantile_shapes"] == [[1, 1, 9]] * 7
    assert result["mean_shapes"] == [[1, 1]] * 7

    assert result["weight_sha256"] == (WEIGHT_SHA256)
    assert result["config_sha256"] == (CONFIG_SHA256)


def test_chronos_2_runtime_certification() -> None:
    certification = _load_json(EVIDENCE_DIR / "runtime-certification.json")

    assert certification["certification_status"] == "RUNTIME_CERTIFIED"
    assert certification["runtime_vram_certified"] is True

    assert certification["model_id"] == MODEL_ID
    assert certification["repo_id"] == REPO_ID
    assert certification["revision"] == REVISION

    assert certification["pipeline_class"] == ("Chronos2Pipeline")
    assert certification["model_class"] == ("Chronos2Model")

    assert certification["device"] == "cuda:0"
    assert certification["gpu_used"] is True
    assert certification["cpu_fallback"] is False
    assert certification["cpu_preprocessing"] is True

    assert certification["weight_sha256"] == (WEIGHT_SHA256)
    assert certification["config_sha256"] == (CONFIG_SHA256)

    assert certification["external_gpu_evidence"]["captured"] is True


def test_chronos_2_license_review() -> None:
    review = _load_json(EVIDENCE_DIR / "license-review.json")

    assert review["model_id"] == MODEL_ID
    assert review["repo_id"] == REPO_ID
    assert review["revision"] == REVISION
    assert review["license"] == "apache-2.0"
    assert review["review_status"] == "APPROVED"
    assert review["commercial_use"] is True
    assert review["attribution_required"] is True


def test_chronos_2_external_gpu_process_evidence() -> None:
    response = _load_json(EVIDENCE_DIR / "provider-response.json")

    gpu_pid = response["gpu_evidence"]["gpu_pid"]

    samples = (EVIDENCE_DIR / "nvidia-process-samples.csv").read_text(
        encoding="utf-8",
        errors="replace",
    )

    matching_lines = [line for line in samples.splitlines() if f", {gpu_pid}," in line]

    assert len(matching_lines) >= 1

    observed_memory = []
    observed_commands = []

    for line in matching_lines:
        fields = [field.strip() for field in line.split(",")]

        assert int(fields[1]) == gpu_pid
        if fields[2] != "[No data]":
            observed_commands.append(fields[2])

        observed_memory.append(int(fields[3]))

    assert any(
        command.endswith("/environments/autogluon-timeseries/.venv/bin/python")
        for command in observed_commands
    )
    assert max(observed_memory) > 0


def test_chronos_2_runtime_status_ledger() -> None:
    status = _load_json(STATUS_PATH)

    assert len(status["results"]) == 21
    assert status["runtime_certified_models"] == sum(
        item.get("runtime_status") == "CERTIFIED" for item in status["results"]
    )

    certified = [item for item in status["results"] if item.get("runtime_status") == "CERTIFIED"]

    assert len(certified) == status["runtime_certified_models"]

    row = next(item for item in status["results"] if item["model_id"] == MODEL_ID)

    assert row["runtime_status"] == "CERTIFIED"
    assert row["runtime_vram_certified"] is True
    assert row["runtime_revision"] == REVISION
    assert row["runtime_device"] == "cuda:0"
    assert row["runtime_input_devices"] == ["cpu"] * 7
    assert row["runtime_cpu_preprocessing"] is True
    assert row["runtime_gpu_used"] is True
    assert row["runtime_cpu_fallback"] is False
    assert row["runtime_peak_vram_bytes"] > 0
    assert row["runtime_gpu_pid"] > 0

    assert row["runtime_weight_sha256"] == (WEIGHT_SHA256)
    assert row["runtime_config_sha256"] == (CONFIG_SHA256)
    assert row["runtime_license_review"] == "APPROVED"


def test_chronos_2_evidence_sha256_manifest() -> None:
    manifest = EVIDENCE_DIR / "sha256sum.txt"

    assert manifest.is_file()

    evidence_files = [
        path.name
        for path in EVIDENCE_DIR.iterdir()
        if path.is_file() and path.name != "sha256sum.txt"
    ]

    assert len(evidence_files) >= 14

    manifest_text = manifest.read_text(encoding="utf-8")

    for evidence_file in evidence_files:
        assert f"  {evidence_file}" in manifest_text
