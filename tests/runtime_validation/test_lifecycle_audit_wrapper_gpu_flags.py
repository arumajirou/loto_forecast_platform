from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools" / "run_all_model_argument_lifecycle_audit.sh"


def test_wrapper_supports_strict_gpu_verification() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert 'VERIFY_GPU="${VERIFY_GPU:-0}"' in text
    assert 'GPUS_PER_TRIAL="${GPUS_PER_TRIAL:-0}"' in text
    assert 'PARALLEL_GPU_MODELS="${PARALLEL_GPU_MODELS:-1}"' in text
    assert "VERIFY_GPU_FLAG=(--verify-gpu)" in text
    assert '"${VERIFY_GPU_FLAG[@]}"' in text
    assert '--gpus-per-trial "$GPUS_PER_TRIAL"' in text
    assert '--parallel-gpu-models "$PARALLEL_GPU_MODELS"' in text


def test_wrapper_rejects_invalid_strict_gpu_configuration() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert '[[ "$VERIFY_GPU" == "1" && "$DEVICE" != "cuda" ]]' in text
    assert '[[ "$VERIFY_GPU" == "1" && "$GPUS_PER_TRIAL" -lt 1 ]]' in text
