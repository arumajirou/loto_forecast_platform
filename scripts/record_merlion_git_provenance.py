from __future__ import annotations

import argparse
from pathlib import Path

from loto.merlion_campaign.git_provenance import (
    build_git_provenance,
    write_git_provenance,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_git_provenance(args.root)
    write_git_provenance(args.output, report)
    print(f"GIT_PROVENANCE_STATUS={report['status']}")
    print(f"GIT_PROVENANCE_HEAD={report['head_sha']}")
    print(f"GIT_PROVENANCE_BRANCH={report['branch']}")
    print(f"GIT_PROVENANCE_REPORT={args.output.resolve()}")
    return 0 if report["status"] == "CLEAN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
