from __future__ import annotations

import argparse
import json
from pathlib import Path

from loto.sktime_campaign.approval_authorization import HumanApproval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.draft.read_text(encoding="utf-8"))
    payload["signature"] = args.signature.read_text(encoding="utf-8")
    approval = HumanApproval.model_validate(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            approval.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"SKTIME_P7_FINAL_APPROVAL={args.output}")


if __name__ == "__main__":
    main()
