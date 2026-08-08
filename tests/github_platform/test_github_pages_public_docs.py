from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "github_pages" / "public_docs.py"
POLICY_PATH = ROOT / "configs" / "github_pages" / "public_docs_policy_v1.yaml"
SOURCE_PATH = ROOT / "docs-public"
SOURCE_COMMIT = "a" * 40
GENERATED_AT = "2026-08-06T09:00:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location("github_pages_public_docs", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_site(tmp_path: Path) -> Path:
    destination = tmp_path / "docs-public"
    shutil.copytree(SOURCE_PATH, destination)
    return destination


def test_repository_public_docs_pass_strict_audit() -> None:
    module = _load_module()
    policy = module.load_policy(POLICY_PATH)
    result = module.audit_public_docs(
        policy=policy,
        source=SOURCE_PATH,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
    )
    assert result.status == "PASS"
    assert not result.findings
    assert {item.path for item in result.files} == set(policy.required_files)


def test_unknown_policy_key_fails_closed(tmp_path: Path) -> None:
    module = _load_module()
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError):
        module.load_policy(policy_path)


def test_secret_local_path_and_private_host_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    source = _copy_site(tmp_path)
    index = source / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8")
        + "\n<p>-----BEGIN PRIVATE KEY----- /mnt/private http://127.0.0.1</p>\n",
        encoding="utf-8",
    )
    result = module.audit_public_docs(
        policy=module.load_policy(POLICY_PATH),
        source=source,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
    )
    assert result.status == "FAIL"
    codes = {finding.code for finding in result.findings}
    assert "BLOCKED_TEXT_PATTERN" in codes


def test_broken_traversal_and_external_embed_are_rejected(tmp_path: Path) -> None:
    module = _load_module()
    source = _copy_site(tmp_path)
    index = source / "index.html"
    index.write_text(
        index.read_text(encoding="utf-8")
        + '\n<a href="../../private.txt">escape</a>'
        + '\n<a href="missing.html">missing</a>'
        + '\n<img src="https://example.com/image.png" alt="external">\n',
        encoding="utf-8",
    )
    result = module.audit_public_docs(
        policy=module.load_policy(POLICY_PATH),
        source=source,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
    )
    codes = {finding.code for finding in result.findings}
    assert result.status == "FAIL"
    assert "PATH_TRAVERSAL_LINK" in codes
    assert "BROKEN_LOCAL_REFERENCE" in codes
    assert "EXTERNAL_HOST_NOT_ALLOWED" in codes


def test_build_is_deterministic_and_contains_no_unapproved_files(tmp_path: Path) -> None:
    module = _load_module()
    policy = module.load_policy(POLICY_PATH)
    first = tmp_path / "site-a"
    second = tmp_path / "site-b"
    first_result = module.build_public_site(
        policy=policy,
        source=SOURCE_PATH,
        output=first,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
    )
    second_result = module.build_public_site(
        policy=policy,
        source=SOURCE_PATH,
        output=second,
        source_commit=SOURCE_COMMIT,
        generated_at=GENERATED_AT,
    )
    assert first_result.manifest_sha256 == second_result.manifest_sha256
    first_manifest = json.loads((first / "PUBLIC_SITE_MANIFEST.json").read_text())
    second_manifest = json.loads((second / "PUBLIC_SITE_MANIFEST.json").read_text())
    assert first_manifest == second_manifest
    assert (first / ".nojekyll").is_file()
    assert (first / "SHA256SUMS").read_text() == (second / "SHA256SUMS").read_text()
    output_files = {
        path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file()
    }
    assert output_files == {
        *policy.required_files,
        ".nojekyll",
        "PUBLIC_SITE_MANIFEST.json",
        "SHA256SUMS",
    }
