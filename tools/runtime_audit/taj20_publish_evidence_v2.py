from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BASE_PATH = Path(__file__).with_name("taj20_publish_evidence.py")
_SPEC = importlib.util.spec_from_file_location("taj20_publish_evidence_base", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load base publisher: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

PublishError = base.PublishError

FORBIDDEN_SECRET_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "github_pat_",
    "ghp_",
    "AKIA",
)


def _assert_no_secret_markers(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_SECRET_MARKERS:
            if marker in text:
                raise PublishError(
                    f"secret-like marker rejected before publication: {path.name}: {marker}"
                )


def _copy_checksum_contract(source: Path, destination: Path) -> tuple[str, ...]:
    """Copy exactly the files authenticated by source/SHA256SUMS."""
    source = source.resolve()
    sums = source / "SHA256SUMS"
    if not sums.is_file():
        raise PublishError(f"SHA256SUMS missing: {source}")

    base._verify_sha256s(source)
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            _expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise PublishError(f"invalid SHA256SUMS line {number}: {sums}") from exc
        if relative == "SHA256SUMS":
            raise PublishError("SHA256SUMS must not authenticate itself")

        src = (source / relative).resolve()
        try:
            src.relative_to(source)
        except ValueError as exc:
            raise PublishError(f"SHA256SUMS path escapes source root: {relative}") from exc
        if not src.is_file():
            raise PublishError(f"publication source file missing: {src}")

        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(relative)

    shutil.copy2(sums, destination / "SHA256SUMS")
    base._verify_sha256s(destination)
    return tuple(copied)


def _materialize_publication_v2(
    *,
    run_root: Path,
    publication_root: Path,
    validated: dict[str, Any],
    repo_head: str,
    remote_branch: str,
) -> tuple[str, str]:
    source_root = publication_root / "source"
    contracts = {
        "identity-plan": validated["identity_root"],
        "preflight": validated["preflight_root"],
        "probabilistic-runtime": validated["probabilistic_root"],
        "unified-acceptance": validated["unified_root"],
        "unified-reverify": validated["reverify_root"],
    }
    copied_contracts = {
        name: list(_copy_checksum_contract(source, source_root / name))
        for name, source in contracts.items()
    }

    publication = {
        "schema_version": "taj20-runtime-publication/v2",
        "run_id": run_root.name,
        "repo_head": repo_head,
        "remote_branch": remote_branch,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "publication_contract": "source SHA256SUMS is authoritative for each evidence directory",
        "copied_checksum_contracts": copied_contracts,
        "identity_contract": {
            "probabilistic_pairs": base.EXPECTED_PROBABILISTIC_PAIRS,
            "unified_models": base.EXPECTED_UNIFIED_MODELS,
            "games": base.EXPECTED_GAMES,
            "unified_pairs": base.EXPECTED_UNIFIED_PAIRS,
        },
        "source_hashes": {
            "probabilistic_artifact_manifest_sha256": validated[
                "probabilistic_manifest_sha256"
            ],
            "probabilistic_sha256s_sha256": validated["probabilistic_sha256s_sha256"],
            "unified_artifact_manifest_sha256": validated["unified_manifest_sha256"],
            "unified_sha256s_sha256": validated["unified_sha256s_sha256"],
            "reverify_artifact_manifest_sha256": validated["reverify_manifest_sha256"],
            "reverify_sha256s_sha256": validated["reverify_sha256s_sha256"],
        },
        "scientific_boundary": {
            "holdout": "CLOSED",
            "prospective": "CLOSED",
            "promotion": "CLOSED",
            "accuracy_claim": False,
        },
    }
    publication_root.mkdir(parents=True, exist_ok=True)
    (publication_root / "PUBLICATION.json").write_text(
        json.dumps(publication, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    _assert_no_secret_markers(publication_root)
    return base._write_publication_integrity(publication_root)


def _remove_stale_local_branch(repo_root: Path, branch: str, repo_head: str) -> bool:
    probe = base._git(
        repo_root,
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        check=False,
    )
    if probe.returncode == 1:
        return False
    if probe.returncode != 0:
        raise PublishError(f"cannot inspect local evidence branch: rc={probe.returncode}")
    local_sha = base._git(repo_root, "rev-parse", f"refs/heads/{branch}").stdout.strip()
    if local_sha != repo_head:
        raise PublishError(
            "stale local evidence branch contains unique commits; refusing deletion: "
            f"{branch} {local_sha} != {repo_head}"
        )
    base._git(repo_root, "branch", "-D", branch)
    return True


def publish(*, repo_root: Path, run_root: Path) -> dict[str, str]:
    repo_root = repo_root.resolve()
    run_root = run_root.resolve()
    current_branch = base._git(repo_root, "branch", "--show-current").stdout.strip()
    if current_branch != "main":
        raise PublishError(f"publication must start from local main, got {current_branch!r}")

    base._git(repo_root, "fetch", "origin", "main")
    repo_head = base._git(repo_root, "rev-parse", "HEAD").stdout.strip()
    origin_main = base._git(repo_root, "rev-parse", "origin/main").stdout.strip()
    if repo_head != origin_main:
        raise PublishError(f"local main is not origin/main: {repo_head} != {origin_main}")

    branch = f"evidence/taj20-runtime-{run_root.name}"
    remote_probe = base._git(
        repo_root,
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{branch}",
        check=False,
    )
    if remote_probe.returncode == 0:
        raise PublishError(f"remote evidence branch already exists: {branch}")
    if remote_probe.returncode != 2:
        raise PublishError(f"cannot probe remote evidence branch: rc={remote_probe.returncode}")

    _remove_stale_local_branch(repo_root, branch, repo_head)
    base._materialize_publication = _materialize_publication_v2
    result = base.publish(repo_root=repo_root, run_root=run_root)

    cleanup = base._git(repo_root, "branch", "-D", result["branch"], check=False)
    if cleanup.returncode not in {0, 1}:
        raise PublishError(
            f"published evidence but local branch cleanup failed: rc={cleanup.returncode}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()

    result = publish(repo_root=args.repo_root, run_root=args.run_root)
    print("TAJ20_EVIDENCE_PUBLICATION=PASS")
    print("PUBLISHER_VERSION=v2-checksum-contract")
    print(f"REMOTE_BRANCH={result['branch']}")
    print(f"REMOTE_COMMIT={result['commit_sha']}")
    print("REMOTE_COMMIT_VERIFIED=PASS")
    print("PULL_BACK_VERIFIED=PASS")
    print(f"PUBLICATION_ARTIFACT_MANIFEST_SHA256={result['publication_manifest_sha256']}")
    print(f"PUBLICATION_SHA256SUMS_SHA256={result['publication_sha256s_sha256']}")
    print(f"PROBABILISTIC_ARTIFACT_MANIFEST_SHA256={result['probabilistic_manifest_sha256']}")
    print(f"PROBABILISTIC_SHA256SUMS_SHA256={result['probabilistic_sha256s_sha256']}")
    print(f"UNIFIED_ARTIFACT_MANIFEST_SHA256={result['unified_manifest_sha256']}")
    print(f"UNIFIED_SHA256SUMS_SHA256={result['unified_sha256s_sha256']}")
    print("HOLDOUT=CLOSED")
    print("PROSPECTIVE=CLOSED")
    print("PROMOTION=CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
