import pytest

from loto.harness.engines.llamacpp import LlamaCppLaunchConfig
from loto.harness.errors import UnsafeOperation


def test_llamacpp_command_has_64k_and_cache_controls() -> None:
    config = LlamaCppLaunchConfig(
        binary="/opt/llama/llama-server",
        model="/models/qwen.gguf",
        context_size=65536,
    )
    command = config.command()
    assert command[0] == "/opt/llama/llama-server"
    assert command[command.index("--ctx-size") + 1] == "65536"
    assert "--cache-idle-slots" in command
    assert "--jinja" in command


def test_llamacpp_public_bind_is_blocked(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_ALLOW_PUBLIC_BIND", raising=False)
    with pytest.raises(UnsafeOperation):
        LlamaCppLaunchConfig(binary="llama-server", model="m.gguf", host="0.0.0.0")
