from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicDocsPolicy(StrictModel):
    schema_version: Literal[1]
    source_root: str
    allowed_extensions: list[str]
    allowed_extensionless_files: list[str] = Field(default_factory=list)
    required_files: list[str]
    max_file_bytes: int = Field(gt=0, le=10 * 1024 * 1024)
    external_link_hosts: list[str] = Field(default_factory=list)
    external_embed_hosts: list[str] = Field(default_factory=list)
    blocked_path_components: list[str]
    blocked_text_patterns: list[str]

    @field_validator(
        "allowed_extensions",
        "allowed_extensionless_files",
        "required_files",
        "external_link_hosts",
        "external_embed_hosts",
        "blocked_path_components",
        "blocked_text_patterns",
    )
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("policy lists must not contain duplicate values")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "PublicDocsPolicy":
        if not self.source_root or PurePosixPath(self.source_root).is_absolute():
            raise ValueError("source_root must be a non-empty relative path")
        if any(not extension.startswith(".") for extension in self.allowed_extensions):
            raise ValueError("allowed_extensions must use dot-prefixed suffixes")
        for pattern in self.blocked_text_patterns:
            re.compile(pattern)
        return self


class Finding(StrictModel):
    code: str
    path: str
    detail: str


class FileEvidence(StrictModel):
    path: str
    size_bytes: int
    sha256: str


class AuditResult(StrictModel):
    schema_version: Literal[1] = 1
    status: Literal["PASS", "FAIL"]
    source_root: str
    source_commit: str
    generated_at: str
    files: list[FileEvidence]
    findings: list[Finding]
    manifest_sha256: str


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for key, value in attrs:
            if value is None:
                continue
            if key.lower() == "href":
                self.links.append(("link", value))
            elif key.lower() == "src":
                self.links.append(("embed", value))


def load_policy(path: Path) -> PublicDocsPolicy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PublicDocsPolicy.model_validate(raw)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def validate_source_commit(source_commit: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")


def _normalized_relative_target(current: PurePosixPath, raw_target: str) -> PurePosixPath:
    decoded = unquote(raw_target)
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc:
        raise ValueError("external target cannot be normalized as a local path")
    target_path = parsed.path
    if not target_path:
        return current
    if target_path.startswith("/"):
        raise ValueError("root-absolute local links are not allowed")
    candidate = current.parent / target_path
    parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("local link escapes the public root")
            parts.pop()
        else:
            parts.append(part)
    return PurePosixPath(*parts)


def _validate_reference(
    *,
    source: Path,
    current: PurePosixPath,
    kind: str,
    raw_target: str,
    policy: PublicDocsPolicy,
) -> Finding | None:
    target = raw_target.strip()
    lowered = target.lower()
    if lowered.startswith(("javascript:", "data:", "file:")):
        return Finding(
            code="DISALLOWED_URL_SCHEME",
            path=current.as_posix(),
            detail=f"{kind} uses a disallowed URL scheme",
        )
    if lowered.startswith(("mailto:", "tel:")):
        return None

    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower()
        allowed = (
            policy.external_embed_hosts if kind == "embed" else policy.external_link_hosts
        )
        if host not in allowed:
            return Finding(
                code="EXTERNAL_HOST_NOT_ALLOWED",
                path=current.as_posix(),
                detail=f"{kind} host {host!r} is not allowlisted",
            )
        return None
    if parsed.scheme or parsed.netloc:
        return Finding(
            code="DISALLOWED_URL_SCHEME",
            path=current.as_posix(),
            detail=f"{kind} uses unsupported URL syntax",
        )

    try:
        relative_target = _normalized_relative_target(current, target)
    except ValueError as exc:
        return Finding(
            code="PATH_TRAVERSAL_LINK",
            path=current.as_posix(),
            detail=str(exc),
        )
    target_path = source / relative_target
    if parsed.path.endswith("/"):
        target_path = target_path / "index.html"
    if not parsed.path:
        target_path = source / current
    if not target_path.is_file():
        return Finding(
            code="BROKEN_LOCAL_REFERENCE",
            path=current.as_posix(),
            detail=f"{kind} target {relative_target.as_posix()!r} does not exist",
        )
    return None


def audit_public_docs(
    *,
    policy: PublicDocsPolicy,
    source: Path,
    source_commit: str,
    generated_at: str,
) -> AuditResult:
    validate_source_commit(source_commit)
    source = source.resolve()
    findings: list[Finding] = []
    evidence: list[FileEvidence] = []

    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    if source.name != Path(policy.source_root).name:
        findings.append(
            Finding(
                code="SOURCE_ROOT_MISMATCH",
                path=".",
                detail=f"expected source directory name {policy.source_root!r}",
            )
        )

    blocked_components = {value.lower() for value in policy.blocked_path_components}
    allowed_extensions = {value.lower() for value in policy.allowed_extensions}
    allowed_extensionless = set(policy.allowed_extensionless_files)
    patterns = [re.compile(value) for value in policy.blocked_text_patterns]

    for current_root, dir_names, file_names in os.walk(source, followlinks=False):
        current_path = Path(current_root)
        for name in list(dir_names):
            path = current_path / name
            relative = path.relative_to(source).as_posix()
            if path.is_symlink():
                findings.append(
                    Finding(
                        code="SYMLINK_NOT_ALLOWED",
                        path=relative,
                        detail="directory symlinks are prohibited",
                    )
                )
                dir_names.remove(name)
        for name in sorted(file_names):
            path = current_path / name
            relative_path = path.relative_to(source)
            relative = relative_path.as_posix()
            if path.is_symlink():
                findings.append(
                    Finding(
                        code="SYMLINK_NOT_ALLOWED",
                        path=relative,
                        detail="file symlinks are prohibited",
                    )
                )
                continue
            if any(part.lower() in blocked_components for part in relative_path.parts):
                findings.append(
                    Finding(
                        code="BLOCKED_PATH_COMPONENT",
                        path=relative,
                        detail="path contains a prohibited component",
                    )
                )
            suffix = path.suffix.lower()
            if suffix not in allowed_extensions and name not in allowed_extensionless:
                findings.append(
                    Finding(
                        code="FILE_TYPE_NOT_ALLOWED",
                        path=relative,
                        detail=f"suffix {suffix!r} is not allowed",
                    )
                )
            size = path.stat().st_size
            if size > policy.max_file_bytes:
                findings.append(
                    Finding(
                        code="FILE_TOO_LARGE",
                        path=relative,
                        detail=f"{size} bytes exceeds {policy.max_file_bytes}",
                    )
                )
            content = path.read_bytes()
            evidence.append(
                FileEvidence(path=relative, size_bytes=size, sha256=sha256_bytes(content))
            )
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(
                    Finding(
                        code="NON_UTF8_CONTENT",
                        path=relative,
                        detail="public files must be UTF-8 text",
                    )
                )
                continue
            for pattern in patterns:
                if pattern.search(text):
                    findings.append(
                        Finding(
                            code="BLOCKED_TEXT_PATTERN",
                            path=relative,
                            detail=f"matched policy expression {pattern.pattern!r}",
                        )
                    )
            if suffix == ".html":
                parser = LinkCollector()
                try:
                    parser.feed(text)
                except Exception as exc:
                    findings.append(
                        Finding(
                            code="HTML_PARSE_ERROR",
                            path=relative,
                            detail=type(exc).__name__,
                        )
                    )
                    continue
                current = PurePosixPath(relative)
                for kind, target in parser.links:
                    finding = _validate_reference(
                        source=source,
                        current=current,
                        kind=kind,
                        raw_target=target,
                        policy=policy,
                    )
                    if finding is not None:
                        findings.append(finding)

    present = {item.path for item in evidence}
    for required in policy.required_files:
        if required not in present:
            findings.append(
                Finding(
                    code="REQUIRED_FILE_MISSING",
                    path=required,
                    detail="required public-site file is missing",
                )
            )

    sorted_files = sorted(evidence, key=lambda item: item.path)
    sorted_findings = sorted(findings, key=lambda item: (item.path, item.code, item.detail))
    manifest_payload = [item.model_dump() for item in sorted_files]
    return AuditResult(
        status="FAIL" if sorted_findings else "PASS",
        source_root=policy.source_root,
        source_commit=source_commit,
        generated_at=generated_at,
        files=sorted_files,
        findings=sorted_findings,
        manifest_sha256=canonical_json_sha256(manifest_payload),
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_audit_evidence(output: Path, result: AuditResult) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    report = result.model_dump()
    manifest = {
        "schema_version": 1,
        "source_root": result.source_root,
        "source_commit": result.source_commit,
        "generated_at": result.generated_at,
        "manifest_sha256": result.manifest_sha256,
        "files": [item.model_dump() for item in result.files],
    }
    _write_json(output / "PUBLIC_DOCS_AUDIT.json", report)
    _write_json(output / "PUBLIC_DOCS_MANIFEST.json", manifest)
    hashes = []
    for name in ("PUBLIC_DOCS_AUDIT.json", "PUBLIC_DOCS_MANIFEST.json"):
        value = (output / name).read_bytes()
        hashes.append(f"{sha256_bytes(value)}  {name}")
    (output / "SHA256SUMS").write_text("\n".join(hashes) + "\n", encoding="utf-8")


def build_public_site(
    *,
    policy: PublicDocsPolicy,
    source: Path,
    output: Path,
    source_commit: str,
    generated_at: str,
) -> AuditResult:
    result = audit_public_docs(
        policy=policy,
        source=source,
        source_commit=source_commit,
        generated_at=generated_at,
    )
    if result.status != "PASS":
        raise ValueError("public documentation audit failed")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for item in result.files:
        source_path = source / item.path
        destination = output / item.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    site_manifest = {
        "schema_version": 1,
        "source_commit": source_commit,
        "generated_at": generated_at,
        "source_manifest_sha256": result.manifest_sha256,
        "files": [item.model_dump() for item in result.files],
    }
    _write_json(output / "PUBLIC_SITE_MANIFEST.json", site_manifest)

    output_hashes: list[str] = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        relative = path.relative_to(output).as_posix()
        output_hashes.append(f"{sha256_bytes(path.read_bytes())}  {relative}")
    (output / "SHA256SUMS").write_text(
        "\n".join(output_hashes) + "\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit and build public GitHub Pages content")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--generated-at", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--output", type=Path, required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_policy(args.policy)
    if args.command == "audit":
        result = audit_public_docs(
            policy=policy,
            source=args.source,
            source_commit=args.source_commit,
            generated_at=args.generated_at,
        )
        write_audit_evidence(args.output, result)
        print(result.model_dump_json())
        return 0 if result.status == "PASS" else 1

    result = build_public_site(
        policy=policy,
        source=args.source,
        output=args.output,
        source_commit=args.source_commit,
        generated_at=args.generated_at,
    )
    print(result.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
