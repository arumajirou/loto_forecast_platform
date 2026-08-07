from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_shared_p6_model_contract_is_byte_identical() -> None:
    paths = [
        ROOT / "src/loto/adapters/gluonts/p6_models.py",
        ROOT / "environments/gluonts-compat/src/loto_gluonts_provider/p6_models.py",
        ROOT / "environments/gluonts-latest/src/loto_gluonts_provider/p6_models.py",
    ]
    content = paths[0].read_bytes()
    assert content == paths[1].read_bytes()
    assert content == paths[2].read_bytes()


def test_provider_p6_entrypoints_are_byte_identical() -> None:
    compat = ROOT / "environments/gluonts-compat/src/loto_gluonts_provider/p6_inventory_cli.py"
    latest = ROOT / "environments/gluonts-latest/src/loto_gluonts_provider/p6_inventory_cli.py"
    assert compat.read_bytes() == latest.read_bytes()
    source = compat.read_text(encoding="utf-8")
    assert "--construct" in source
    assert "return 2" in source


def test_provider_cli_emits_nine_entry_matrix(tmp_path: Path) -> None:
    import json
    import os
    import subprocess
    import sys

    provider_src = ROOT / "environments/gluonts-compat/src"
    output = tmp_path / "matrix.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(provider_src)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "loto_gluonts_provider.p6_inventory_cli",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode in {0, 2}
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["lane"] == "compat"
    assert len(payload["entries"]) == 9
    assert sum(payload["summary"].values()) == 9
