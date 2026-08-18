from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXPECTED_PROBABILISTIC_PAIRS = 456
EXPECTED_UNIFIED_MODELS = 250
EXPECTED_GAMES = 6
EXPECTED_UNIFIED_PAIRS = 1500


class PublishError(RuntimeError):
    """Raised when TAJ-20 runtime evidence cannot be published safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PublishError(f"required JSON missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublishError(f"JSON root must be an object: {path}")
    return payload


def _verify_sha256s(root: Path) -> None:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise PublishError(f"SHA256SUMS missing: {root}")
    resolved_root = root.resolve()
    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError as exc:
            raise PublishError(f"invalid SHA256SUMS line {number}: {sums}") from exc
        target = (root / relative).resolve()
        try:
            target.relative_to(resolved_root)
        except ValueError as exc:
            raise PublishError(f"SHA256SUMS path escapes root: {relative}") from exc
        if not target.is_file():
            raise PublishError(f"hashed file missing: {target}")
        actual = _sha256(target)
        if actual != expected:
            raise PublishError(f"SHA mismatch: {relative}: {actual} != {expected}")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise PublishError(
            f"git {' '.join(args)} failed rc={proc.returncode}: {proc.stderr.strip()}"
        )
    return proc


def _latest_reverify(run_root: Path) -> Path:
    candidates = sorted(path for path in run_root.glob("unified-reverify-*") if path.is_dir())
    if not candidates:
        raise PublishError(f"no unified-reverify-* directory found under {run_root}")
    return candidates[-1]


def _validate_runtime(run_root: Path) -> dict[str, Any]:
    identity_root = run_root / "identity-plan"
    preflight_root = run_root / "preflight"
    probabilistic_root = run_root / "probabilistic-runtime"
    unified_root = run_root / "unified-acceptance"
    reverify_root = _latest_reverify(run_root)

    for root in (
        identity_root,
        preflight_root,
        probabilistic_root,
        unified_root,
        reverify_root,
    ):
        if not root.is_dir():
            raise PublishError(f"required evidence directory missing: {root}")
        _verify_sha256s(root)

    probabilistic = _read_json(probabilistic_root / "CAMPAIGN_SUMMARY.json")
    unified = _read_json(unified_root / "CAMPAIGN_SUMMARY.json")
    reverify = _read_json(reverify_root / "CAMPAIGN_SUMMARY.json")

    if probabilistic.get("acceptance") != "PASS":
        raise PublishError("probabilistic acceptance is not PASS")
    if int(probabilistic.get("observed_pairs", -1)) != EXPECTED_PROBABILISTIC_PAIRS:
        raise PublishError("probabilistic observed_pairs is not 456")

    for label, summary in (("unified", unified), ("reverify", reverify)):
        if summary.get("acceptance") != "PASS":
            raise PublishError(f"{label} acceptance is not PASS")
        counts = summary.get("identity_counts") or {}
        if (
            int(counts.get("unified", -1)) != EXPECTED_UNIFIED_MODELS
            or int(counts.get("games", -1)) != EXPECTED_GAMES
            or int(counts.get("unified_pairs", -1)) != EXPECTED_UNIFIED_PAIRS
        ):
            raise PublishError(f"{label} identity matrix is not exactly 250 x 6 = 1500")
        boundary = summary.get("scientific_boundary") or {}
        if (
            boundary.get("holdout") != "CLOSED"
            or boundary.get("prospective") != "CLOSED"
            or boundary.get("promotion") != "CLOSED"
        ):
            raise PublishError(f"{label} scientific boundary is not closed")

    unified_manifest_sha = _sha256(unified_root / "ARTIFACT_MANIFEST.json")
    unified_sums_sha = _sha256(unified_root / "SHA256SUMS")
    reverify_manifest_sha = _sha256(reverify_root / "ARTIFACT_MANIFEST.json")
    reverify_sums_sha = _sha256(reverify_root / "SHA256SUMS")
    if unified_manifest_sha != reverify_manifest_sha or unified_sums_sha != reverify_sums_sha:
        raise PublishError("unified acceptance and read-only reverify hashes differ")

    return {
        "identity_root": identity_root,
        "preflight_root": preflight_root,
        "probabilistic_root": probabilistic_root,
        "unified_root": unified_root,
        "reverify_root": reverify_root,
        "probabilistic_manifest_sha256": _sha256(
            probabilistic_root / "ARTIFACT_MANIFEST.json"
        ),
        "probabilistic_sha256s_sha256": _sha256(probabilistic_root / "SHA256SUMS"),
        "unified_manifest_sha256": unified_manifest_sha,
        "unified_sha256s_sha256": unified_sums_sha,
        "reverify_manifest_sha256": reverify_manifest_sha,
        "reverify_sha256s_sha256": reverify_sums_sha,
    }


def _copy_required(source: Path, destination: Path, names: tuple[str, ...]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = source / name
        if not src.is_file():
            raise PublishError(f"publication source file missing: {src}")
        shutil.copy2(src, destination / name)


def _write_publication_integrity(root: Path) -> tuple[str, str]:
    manifest = root / "ARTIFACT_MANIFEST.json"
    sums = root / "SHA256SUMS"
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path in {manifest, sums}:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "taj20-runtime-publication-artifacts/v1",
                "file_count": len(rows),
                "files": rows,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_sha = _sha256(manifest)
    lines = [f"{row['sha256']}  {row['path']}" for row in rows]
    lines.append(f"{manifest_sha}  ARTIFACT_MANIFEST.json")
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_sha, _sha256(sums)


def _materialize_publication(
    *,
    run_root: Path,
    publication_root: Path,
    validated: dict[str, Any],
    repo_head: str,
    remote_branch: str,
) -> tuple[str, str]:
    source_root = publication_root / "source"
    _copy_required(
        validated["identity_root"],
        source_root / "identity-plan",
        ("IDENTITY_SUMMARY.json", "ARTIFACT_MANIFEST.json", "SHA256SUMS"),
    )
    _copy_required(
        validated["preflight_root"],
        source_root / "preflight",
        (
            "PRECHECK_SUMMARY.json",
            "INCREMENTAL_MATRIX_PLAN.json",
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
        ),
    )
    _copy_required(
        validated["probabilistic_root"],
        source_root / "probabilistic-runtime",
        (
            "MATRIX_PLAN.json",
            "NORMALIZED_RESULTS.jsonl",
            "CAMPAIGN_SUMMARY.json",
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
        ),
    )
    _copy_required(
        validated["unified_root"],
        source_root / "unified-acceptance",
        (
            "CAMPAIGN_SUMMARY.json",
            "UNIFIED_NORMALIZED_RESULTS.jsonl",
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
        ),
    )
    _copy_required(
        validated["reverify_root"],
        source_root / "unified-reverify",
        (
            "CAMPAIGN_SUMMARY.json",
            "UNIFIED_NORMALIZED_RESULTS.jsonl",
            "ARTIFACT_MANIFEST.json",
            "SHA256SUMS",
        ),
    )

    publication = {
        "schema_version": "taj20-runtime-publication/v1",
        "run_id": run_root.name,
        "repo_head": repo_head,
        "remote_branch": remote_branch,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "identity_contract": {
            "probabilistic_pairs": EXPECTED_PROBABILISTIC_PAIRS,
            "unified_models": EXPECTED_UNIFIED_MODELS,
            "games": EXPECTED_GAMES,
            "unified_pairs": EXPECTED_UNIFIED_PAIRS,
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
    return _write_publication_integrity(publication_root)


def publish(*, repo_root: Path, run_root: Path) -> dict[str, str]:
    repo_root = repo_root.resolve()
    run_root = run_root.resolve()
    validated = _validate_runtime(run_root)

    current_branch = _git(repo_root, "branch", "--show-current").stdout.strip()
    if current_branch != "main":
        raise PublishError(f"publication must start from local main, got {current_branch!r}")
    if _git(repo_root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise PublishError("tracked working tree is not clean")

    _git(repo_root, "fetch", "origin", "main")
    repo_head = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    origin_main = _git(repo_root, "rev-parse", "origin/main").stdout.strip()
    if repo_head != origin_main:
        raise PublishError(f"local main is not origin/main: {repo_head} != {origin_main}")

    run_id = run_root.name
    branch = f"evidence/taj20-runtime-{run_id}"
    remote_probe = _git(
        repo_root,
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{branch}",
        check=False,
    )
    if remote_probe.returncode == 0:
        raise PublishError(f"remote evidence branch already exists: {branch}")
    if remote_probe.returncode not in {2}:
        raise PublishError(f"cannot probe remote evidence branch: rc={remote_probe.returncode}")

    remote_url = _git(repo_root, "remote", "get-url", "origin").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="taj20-evidence-") as temp_text:
        temp = Path(temp_text)
        worktree = temp / "publish"
        pullback = temp / "pullback"
        _git(repo_root, "worktree", "add", "-b", branch, str(worktree), repo_head)
        try:
            publication_root = worktree / "evidence" / "taj20-runtime" / run_id
            manifest_sha, sums_sha = _materialize_publication(
                run_root=run_root,
                publication_root=publication_root,
                validated=validated,
                repo_head=repo_head,
                remote_branch=branch,
            )
            _verify_sha256s(publication_root)
            _git(worktree, "add", "--force", str(publication_root.relative_to(worktree)))
            _git(
                worktree,
                "-c",
                "user.name=TAJ-20 Evidence Publisher",
                "-c",
                "user.email=97777832+arumajirou@users.noreply.github.com",
                "commit",
                "-m",
                f"evidence: publish TAJ-20 runtime {run_id}",
            )
            commit_sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
            _git(worktree, "push", "-u", "origin", branch)

            remote_line = _git(
                repo_root,
                "ls-remote",
                "origin",
                f"refs/heads/{branch}",
            ).stdout.strip()
            remote_sha = remote_line.split()[0] if remote_line else ""
            if remote_sha != commit_sha:
                raise PublishError(f"remote SHA mismatch: {remote_sha} != {commit_sha}")

            clone = subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--depth",
                    "1",
                    "--branch",
                    branch,
                    remote_url,
                    str(pullback),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if clone.returncode != 0:
                raise PublishError(f"pull-back clone failed: {clone.stderr.strip()}")
            pulled_root = pullback / "evidence" / "taj20-runtime" / run_id
            _verify_sha256s(pulled_root)
            pulled_manifest_sha = _sha256(pulled_root / "ARTIFACT_MANIFEST.json")
            pulled_sums_sha = _sha256(pulled_root / "SHA256SUMS")
            if pulled_manifest_sha != manifest_sha or pulled_sums_sha != sums_sha:
                raise PublishError("pull-back publication hashes differ from source publication")
        finally:
            _git(repo_root, "worktree", "remove", "--force", str(worktree), check=False)
            _git(repo_root, "worktree", "prune", check=False)

    return {
        "branch": branch,
        "commit_sha": commit_sha,
        "publication_manifest_sha256": manifest_sha,
        "publication_sha256s_sha256": sums_sha,
        "probabilistic_manifest_sha256": validated["probabilistic_manifest_sha256"],
        "probabilistic_sha256s_sha256": validated["probabilistic_sha256s_sha256"],
        "unified_manifest_sha256": validated["unified_manifest_sha256"],
        "unified_sha256s_sha256": validated["unified_sha256s_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()

    result = publish(repo_root=args.repo_root, run_root=args.run_root)
    print("TAJ20_EVIDENCE_PUBLICATION=PASS")
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
