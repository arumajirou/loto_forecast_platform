"""Chrony parsing and bounded subprocess adapter outside the pure core evaluator."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .canonical import sha256_bytes
from .contracts import (
    ClockCommandEvidence,
    ClockContinuityEvidence,
    ClockObservation,
    ClockParserEvidence,
    ClockSourceObservation,
    LeapStatus,
    SourceSelectionState,
)

PARSER_ID = "chronyc-text-v1"
PARSER_VERSION = "1.0.0"
_TRACKING_ARGV = ("chronyc", "-n", "tracking")
_SOURCES_ARGV = ("chronyc", "-n", "sources", "-v")


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    started_at_utc: datetime
    duration_seconds: float
    exit_code: int | None
    timed_out: bool
    stdout: bytes
    stderr: bytes


class CommandRunner(Protocol):
    def run(self, argv: tuple[str, ...], timeout_seconds: float) -> CommandResult: ...


class SubprocessCommandRunner:
    """Execute fixed argv without shell interpolation."""

    def run(self, argv: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(argv),
                capture_output=True,
                check=False,
                shell=False,
                timeout=timeout_seconds,
            )
            return CommandResult(
                argv=argv,
                started_at_utc=started_at,
                duration_seconds=max(0.0, time.monotonic() - started),
                exit_code=completed.returncode,
                timed_out=False,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
            return CommandResult(
                argv=argv,
                started_at_utc=started_at,
                duration_seconds=max(0.0, time.monotonic() - started),
                exit_code=None,
                timed_out=True,
                stdout=stdout,
                stderr=stderr,
            )


@dataclass(frozen=True)
class ChronycProbeArtifacts:
    observation: ClockObservation
    tracking_stdout: bytes
    sources_stdout: bytes
    tracking_stderr: bytes
    sources_stderr: bytes


class ChronycAdapter:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self._runner = runner or SubprocessCommandRunner()

    def observe(
        self,
        *,
        observation_id: str,
        timeout_seconds: float,
        continuity_step_threshold_ns: int,
    ) -> ChronycProbeArtifacts:
        wall_start = time.time_ns()
        monotonic_start = time.monotonic_ns()
        started_at = datetime.now(UTC)
        tracking = self._runner.run(_TRACKING_ARGV, timeout_seconds)
        sources = self._runner.run(_SOURCES_ARGV, timeout_seconds)
        ended_at = datetime.now(UTC)
        wall_end = time.time_ns()
        monotonic_end = time.monotonic_ns()
        continuity = ClockContinuityEvidence.create(
            sample_id=f"{observation_id}-continuity",
            started_at_utc=started_at,
            ended_at_utc=ended_at,
            wall_delta_ns=max(0, wall_end - wall_start),
            monotonic_delta_ns=max(0, monotonic_end - monotonic_start),
            step_threshold_ns=continuity_step_threshold_ns,
        )
        observation = parse_chronyc_observation(
            observation_id=observation_id,
            observed_at_utc=ended_at,
            tracking_raw=tracking.stdout,
            sources_raw=sources.stdout,
            commands=(tracking, sources),
            continuity=continuity,
        )
        return ChronycProbeArtifacts(
            observation=observation,
            tracking_stdout=tracking.stdout,
            sources_stdout=sources.stdout,
            tracking_stderr=tracking.stderr,
            sources_stderr=sources.stderr,
        )


def parse_chronyc_observation(
    *,
    observation_id: str,
    observed_at_utc: datetime,
    tracking_raw: bytes,
    sources_raw: bytes,
    commands: tuple[CommandResult, ...] = (),
    continuity: ClockContinuityEvidence | None,
) -> ClockObservation:
    tracking_text = tracking_raw.decode("utf-8", errors="replace")
    sources_text = sources_raw.decode("utf-8", errors="replace")
    values, errors = _parse_tracking(tracking_text, observed_at_utc)
    sources, source_errors = _parse_sources(sources_text)
    errors.extend(source_errors)
    command_evidence = tuple(_command_evidence(index, item) for index, item in enumerate(commands))
    parser = ClockParserEvidence(
        parser_id=PARSER_ID,
        parser_version=PARSER_VERSION,
        parser_code_sha256=_parser_code_sha256(),
        raw_tracking_sha256=sha256_bytes(tracking_raw),
        raw_sources_sha256=sha256_bytes(sources_raw),
        raw_tracking_size_bytes=len(tracking_raw),
        raw_sources_size_bytes=len(sources_raw),
        commands=command_evidence,
        parse_errors=tuple(errors),
    )
    synchronized = values.get("synchronized")
    return ClockObservation.create(
        observation_id=observation_id,
        observed_at_utc=observed_at_utc,
        synchronized=synchronized if isinstance(synchronized, bool) else None,
        leap_status=values.get("leap_status", LeapStatus.UNKNOWN),
        stratum=_optional_int(values.get("stratum")),
        last_offset_seconds=_optional_float(values.get("last_offset_seconds")),
        rms_offset_seconds=_optional_float(values.get("rms_offset_seconds")),
        root_delay_seconds=_optional_float(values.get("root_delay_seconds")),
        root_dispersion_seconds=_optional_float(values.get("root_dispersion_seconds")),
        skew_ppm=_optional_float(values.get("skew_ppm")),
        online_source_count=sum(source.online for source in sources),
        sample_age_seconds=_optional_float(values.get("sample_age_seconds")),
        sources=tuple(sources),
        continuity=continuity,
        parser_evidence=parser,
    )


def verify_raw_observation(
    observation: ClockObservation,
    *,
    tracking_raw: bytes,
    sources_raw: bytes,
) -> None:
    evidence = observation.parser_evidence
    if evidence.parser_id != PARSER_ID or evidence.parser_version != PARSER_VERSION:
        raise ValueError("parser identity does not match this adapter")
    if evidence.parser_code_sha256 != _parser_code_sha256():
        raise ValueError("parser code hash does not match this adapter")
    if sha256_bytes(tracking_raw) != evidence.raw_tracking_sha256:
        raise ValueError("tracking raw bytes do not match parser evidence")
    if sha256_bytes(sources_raw) != evidence.raw_sources_sha256:
        raise ValueError("sources raw bytes do not match parser evidence")
    if len(tracking_raw) != evidence.raw_tracking_size_bytes:
        raise ValueError("tracking raw size does not match parser evidence")
    if len(sources_raw) != evidence.raw_sources_size_bytes:
        raise ValueError("sources raw size does not match parser evidence")


def _parse_tracking(text: str, observed_at_utc: datetime) -> tuple[dict[str, object], list[str]]:
    fields: dict[str, str] = {}
    errors: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        if normalized in fields:
            errors.append(f"duplicate tracking field: {normalized}")
            continue
        fields[normalized] = value.strip()
    result: dict[str, object] = {}
    result["stratum"] = _parse_int_field(fields, "stratum", errors)
    result["last_offset_seconds"] = _parse_seconds_field(fields, "last_offset", errors)
    result["rms_offset_seconds"] = _parse_seconds_field(fields, "rms_offset", errors)
    result["root_delay_seconds"] = _parse_seconds_field(fields, "root_delay", errors)
    result["root_dispersion_seconds"] = _parse_seconds_field(
        fields,
        "root_dispersion",
        errors,
    )
    result["skew_ppm"] = _parse_ppm_field(fields, "skew", errors)
    leap = _parse_leap(fields.get("leap_status"))
    result["leap_status"] = leap
    if leap == LeapStatus.UNKNOWN:
        result["synchronized"] = None
    else:
        result["synchronized"] = leap != LeapStatus.NOT_SYNCHRONIZED
    ref_text = fields.get("ref_time_(utc)") or fields.get("reference_time_(utc)")
    if ref_text is None:
        errors.append("missing tracking field: ref_time_(utc)")
        result["sample_age_seconds"] = None
    else:
        try:
            reference_time = _parse_reference_time(ref_text)
            result["sample_age_seconds"] = max(
                0.0,
                (observed_at_utc - reference_time).total_seconds(),
            )
        except ValueError:
            errors.append("malformed tracking field: ref_time_(utc)")
            result["sample_age_seconds"] = None
    return result, errors


def _parse_sources(text: str) -> tuple[list[ClockSourceObservation], list[str]]:
    sources: list[ClockSourceObservation] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("MS ", "===", "Name/IP", "^" + "=")):
            continue
        if len(line) < 3 or line[0] not in "^=#" or line[1] not in "*+-x?~":
            continue
        columns = line.split()
        if len(columns) < 7:
            errors.append(f"malformed sources row {line_number}")
            continue
        marker = columns[0]
        name = columns[1]
        try:
            stratum = int(columns[2])
            poll_exponent = int(columns[3])
            reach = int(columns[4], 8)
            age = _parse_age(columns[5])
            offset = _parse_compound_offset(columns[6])
            uncertainty = _parse_uncertainty(columns)
        except ValueError:
            errors.append(f"malformed sources row {line_number}")
            continue
        state = _selection_state(marker[1])
        online = reach > 0 and state not in {
            SourceSelectionState.UNREACHABLE,
            SourceSelectionState.FALSETICKER,
        }
        selected = state == SourceSelectionState.CURRENT
        sources.append(
            ClockSourceObservation(
                source_id_sha256=sha256_bytes(name.encode("utf-8")),
                selection_state=state,
                online=online,
                selected=selected,
                stratum=stratum,
                poll_interval_seconds=float(2**poll_exponent),
                sample_age_seconds=age,
                offset_seconds=offset,
                uncertainty_seconds=uncertainty,
            )
        )
    if not sources:
        errors.append("no parseable chronyc source rows")
    return sources, errors


def _command_evidence(index: int, result: CommandResult) -> ClockCommandEvidence:
    return ClockCommandEvidence(
        command_id=f"chronyc-command-{index + 1}",
        argv=result.argv,
        started_at_utc=result.started_at_utc,
        duration_seconds=result.duration_seconds,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        stdout_sha256=sha256_bytes(result.stdout),
        stderr_sha256=sha256_bytes(result.stderr),
        stdout_size_bytes=len(result.stdout),
        stderr_size_bytes=len(result.stderr),
    )


def _parser_code_sha256() -> str:
    """Bind parser evidence to the exact adapter source bytes."""

    return sha256_bytes(Path(__file__).read_bytes())


def _parse_int_field(fields: dict[str, str], key: str, errors: list[str]) -> int | None:
    value = fields.get(key)
    if value is None:
        errors.append(f"missing tracking field: {key}")
        return None
    try:
        return int(value)
    except ValueError:
        errors.append(f"malformed tracking field: {key}")
        return None


def _parse_seconds_field(
    fields: dict[str, str],
    key: str,
    errors: list[str],
) -> float | None:
    value = fields.get(key)
    if value is None:
        errors.append(f"missing tracking field: {key}")
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+seconds?", value)
    if not match:
        errors.append(f"malformed tracking field: {key}")
        return None
    return float(match.group(1))


def _parse_ppm_field(fields: dict[str, str], key: str, errors: list[str]) -> float | None:
    value = fields.get(key)
    if value is None:
        errors.append(f"missing tracking field: {key}")
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s+ppm", value)
    if not match:
        errors.append(f"malformed tracking field: {key}")
        return None
    return abs(float(match.group(1)))


def _parse_leap(value: str | None) -> LeapStatus:
    if value is None:
        return LeapStatus.UNKNOWN
    normalized = " ".join(value.lower().split())
    mapping = {
        "normal": LeapStatus.NORMAL,
        "insert second": LeapStatus.INSERT_SECOND,
        "delete second": LeapStatus.DELETE_SECOND,
        "not synchronised": LeapStatus.NOT_SYNCHRONIZED,
        "not synchronized": LeapStatus.NOT_SYNCHRONIZED,
    }
    return mapping.get(normalized, LeapStatus.UNKNOWN)


def _parse_reference_time(value: str) -> datetime:
    normalized = " ".join(value.split())
    formats = (
        "%a %b %d %H:%M:%S %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    )
    for pattern in formats:
        try:
            return datetime.strptime(normalized, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError("unsupported reference time")


def _selection_state(marker: str) -> SourceSelectionState:
    return {
        "*": SourceSelectionState.CURRENT,
        "+": SourceSelectionState.COMBINED,
        "-": SourceSelectionState.EXCLUDED,
        "?": SourceSelectionState.UNREACHABLE,
        "x": SourceSelectionState.FALSETICKER,
        "~": SourceSelectionState.UNKNOWN,
    }.get(marker, SourceSelectionState.UNKNOWN)


def _parse_age(value: str) -> float:
    if value == "-":
        return 0.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", value)
    if not match:
        raise ValueError("invalid age")
    multiplier = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
    return float(match.group(1)) * multiplier[match.group(2)]


def _parse_compound_offset(value: str) -> float:
    primary = value.split("[")[0]
    return _parse_duration_token(primary)


def _parse_uncertainty(columns: list[str]) -> float | None:
    try:
        index = columns.index("+/-")
    except ValueError:
        return None
    if index + 1 >= len(columns):
        return None
    return abs(_parse_duration_token(columns[index + 1]))


def _parse_duration_token(value: str) -> float:
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)(ns|us|ms|s)", value)
    if not match:
        raise ValueError("invalid duration token")
    multiplier = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}
    return float(match.group(1)) * multiplier[match.group(2)]


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
