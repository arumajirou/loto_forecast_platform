from __future__ import annotations

import importlib.util
from pathlib import Path


PATCHER = Path("tools/evaluation/taj21_phase3_apply.py")


def main() -> None:
    spec = importlib.util.spec_from_file_location("taj21_phase3_apply", PATCHER)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to load TAJ-21 phase 3 patcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.replace_once

    def exact_replace(text: str, old: str, new: str, label: str) -> str:
        if label == "evaluate_seed signature":
            count = text.count(old)
            if count != 2:
                raise SystemExit(
                    f"{label}: expected exactly two pre-patch signature matches, got {count}"
                )
            return text.replace(old, new, 1)
        return original(text, old, new, label)

    module.replace_once = exact_replace
    module.main()


if __name__ == "__main__":
    main()
