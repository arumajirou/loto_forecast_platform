from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from loto.timesfm25_campaign.evidence_review import review_archive  # noqa: E402

DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "timesfm25" / "evidence-review"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely review and seal a TimesFM 2.5 runtime evidence ZIP"
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--sha256", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--expected-run-id")
    args = parser.parse_args()
    sidecar = args.sha256 or args.archive.with_suffix(args.archive.suffix + ".sha256")
    try:
        review_dir, report = review_archive(
            args.archive,
            sidecar,
            args.output_root,
            expected_run_id=args.expected_run_id,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        print("REVIEW_STATUS=FAIL", file=sys.stderr)
        print(f"ERROR_TYPE={type(exc).__name__}", file=sys.stderr)
        print(f"ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"REVIEW_DIR={review_dir}")
    print(f"REVIEW_STATUS={report['review_status']}")
    print(f"FORMAL_STATUS={report['formal_status']}")
    print(f"RUNTIME_STATUS={report['runtime_status']}")
    print(f"ARCHIVE_SHA256={report['archive_sha256']}")
    for reason in report["reasons"]:
        print(f"REASON={reason}")
    raise SystemExit(report["exit_code"])


if __name__ == "__main__":
    main()
