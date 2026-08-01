from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKERS = ROOT / "src" / "loto" / "models" / "workers.py"


def _autohint_source() -> str:
    text = WORKERS.read_text(encoding="utf-8")
    start = text.index("    def _autohint")
    end = text.find("\n    def ", start + 1)

    if end == -1:
        end = len(text)

    return text[start:end]


def test_autohint_does_not_hardcode_cpu_accelerator() -> None:
    block = _autohint_source()

    assert '"accelerator": "cpu"' not in block
    assert '"accelerator": accelerator' in block


def test_autohint_routes_requested_cuda_to_gpu() -> None:
    block = _autohint_source()

    assert "        import torch" in block
    assert 'self.device in {"auto", "cuda"}' in block
    assert "torch.cuda.is_available()" in block
    assert 'else "cpu"' in block
    assert '"devices": 1' in block
