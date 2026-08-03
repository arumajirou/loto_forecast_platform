from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from loto.probabilistic.config import load_run_config, write_resolved_config

PROFILE_CONFIGS: dict[str, str] = {
    "fast_cpu": "configs/probabilistic/native_fast_cpu_api.yaml",
    "fast_gpu": "configs/probabilistic/native_fast_gpu_dashboard.yaml",
    "standard": "configs/probabilistic/native_standard_notified.yaml",
    "resume_stopped": "configs/probabilistic/native_resume_stopped_notified.yaml",
}

SAFE_OVERRIDE_FIELDS = {
    "models",
    "games",
    "seeds",
    "folds",
    "test_size",
    "native_chains",
    "native_warmup",
    "native_draws",
    "native_svi_steps",
    "outer_workers",
    "max_gpu_jobs",
    "max_heavy_cpu_jobs",
    "speech_enabled",
    "email_enabled",
    "resume_policy",
    "save_posterior_draws",
    "notify_every_completed",
    "notify_progress_seconds",
}

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "STOPPED", "EXITED_UNKNOWN"}


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["fast_cpu", "fast_gpu", "standard", "resume_stopped"] = "fast_cpu"
    run_id: str | None = None
    preflight: bool = True
    overrides: dict[str, Any] = Field(default_factory=dict)


class StopRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


class NotificationTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speech: bool = True
    email: bool = False
    speech_engine: str = "auto"


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["fast_cpu", "fast_gpu", "standard", "resume_stopped"] = "fast_cpu"


class TtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    speaker: int = Field(default=3, ge=0, le=999)
    speed_scale: float = Field(default=1.15, ge=0.5, le=2.0)


class ApiRunError(RuntimeError):
    pass


class ApiConflictError(ApiRunError):
    pass


class ApiValidationError(ApiRunError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _tail(path: Path, lines: int) -> str:
    if not path.is_file():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-max(1, min(lines, 5000)) :])


def _voicevox_base_url() -> str:
    return os.environ.get("LOTO_VOICEVOX_URL", "http://127.0.0.1:50021").rstrip("/")


def _voicevox_get_json(path: str, *, timeout: float = 10.0) -> Any:
    with urllib.request.urlopen(_voicevox_base_url() + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _voicevox_synthesize(request: TtsRequest) -> bytes:
    base = _voicevox_base_url()
    query_url = (
        base
        + "/audio_query?"
        + urllib.parse.urlencode({"speaker": request.speaker, "text": request.text})
    )
    audio_query_request = urllib.request.Request(query_url, data=b"", method="POST")
    with urllib.request.urlopen(audio_query_request, timeout=30) as response:
        query = json.loads(response.read().decode("utf-8"))
    query["speedScale"] = request.speed_scale
    synthesis_url = base + "/synthesis?" + urllib.parse.urlencode({"speaker": request.speaker})
    synthesis_request = urllib.request.Request(
        synthesis_url,
        data=json.dumps(query, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(synthesis_request, timeout=120) as response:
        audio = response.read()
    if len(audio) < 44 or not audio.startswith(b"RIFF"):
        raise ApiRunError("VOICEVOX returned an invalid WAV payload")
    return audio


def _play_wav(audio: bytes) -> str:
    candidates = [
        ("paplay", ["paplay"]),
        ("aplay", ["aplay", "-q"]),
        ("mpv", ["mpv", "--no-video", "--really-quiet"]),
        ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]),
    ]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(audio)
        wav_path = Path(handle.name)
    try:
        for name, command in candidates:
            if shutil.which(name):
                subprocess.run([*command, str(wav_path)], check=True, timeout=120)
                return name
    finally:
        wav_path.unlink(missing_ok=True)
    raise ApiRunError("no WAV player found")


class ApiRunManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.api_dir = self.root / "artifacts" / "probabilistic-api"
        self.state_dir = self.api_dir / "states"
        self.config_dir = self.api_dir / "configs"
        self.log_dir = self.api_dir / "logs"
        self.preflight_dir = self.api_dir / "preflight"
        for directory in (
            self.state_dir,
            self.config_dir,
            self.log_dir,
            self.preflight_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.current_path = self.api_dir / "current.json"
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._log_handles: dict[str, Any] = {}

    def profiles(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for profile, relative in PROFILE_CONFIGS.items():
            path = (self.root / relative).resolve()
            if not path.is_file():
                rows.append(
                    {
                        "profile": profile,
                        "available": False,
                        "config": relative,
                    }
                )
                continue
            config = load_run_config(path)
            rows.append(
                {
                    "profile": profile,
                    "available": True,
                    "config": relative,
                    "output": config.output,
                    "models": config.models,
                    "games": config.games,
                    "outer_workers": config.outer_workers,
                    "max_gpu_jobs": config.max_gpu_jobs,
                    "max_heavy_cpu_jobs": config.max_heavy_cpu_jobs,
                    "native_device": config.native_device,
                    "speech_enabled": config.speech_enabled,
                    "email_enabled": config.email_enabled,
                    "resume_policy": config.resume_policy,
                }
            )
        return rows

    def _state_path(self, run_id: str) -> Path:
        return self.state_dir / f"{run_id}.json"

    def _load_state(self, run_id: str) -> dict[str, Any]:
        state = _read_json(self._state_path(run_id))
        if state is None:
            raise KeyError(run_id)
        return self._refresh_state(state)

    def _refresh_state(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") == "RUNNING" and not _pid_alive(int(state.get("pid") or 0)):
            run_dir = Path(str(state.get("run_dir", "")))
            summary = _read_json(run_dir / "report" / "summary.json")
            if summary:
                final = str(summary.get("status", "EXITED_UNKNOWN"))
                status = "SUCCEEDED" if final == "PASS" else "FAILED"
            elif state.get("stop_requested_at"):
                status = "STOPPED"
            else:
                status = "EXITED_UNKNOWN"
            state = {
                **state,
                "status": status,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            _atomic_json(self._state_path(str(state["run_id"])), state)
            current = _read_json(self.current_path)
            if current and current.get("run_id") == state.get("run_id"):
                _atomic_json(self.current_path, state)
        return state

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            state = _read_json(self.current_path)
            return self._refresh_state(state) if state else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(
            self.state_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: max(1, min(limit, 500))]:
            state = _read_json(path)
            if state:
                rows.append(self._refresh_state(state))
        return rows

    def _validate_run_id(self, run_id: str) -> None:
        if not RUN_ID_RE.fullmatch(run_id):
            raise ApiValidationError("run_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

    def _resolve_config(self, request: StartRunRequest) -> tuple[Any, Path]:
        relative = PROFILE_CONFIGS.get(request.profile)
        if relative is None:
            raise ApiValidationError(f"unknown profile: {request.profile}")
        source = (self.root / relative).resolve()
        try:
            source.relative_to(self.root)
        except ValueError as exc:
            raise ApiValidationError("profile config escaped project root") from exc
        if not source.is_file():
            raise ApiValidationError(f"profile config not found: {relative}")

        unknown = sorted(set(request.overrides) - SAFE_OVERRIDE_FIELDS)
        if unknown:
            raise ApiValidationError("unsupported override fields: " + ", ".join(unknown))

        config = load_run_config(source)
        updates = dict(request.overrides)
        if request.run_id:
            self._validate_run_id(request.run_id)
            updates["run_id"] = request.run_id
        elif request.profile != "resume_stopped":
            updates["run_id"] = "api-" + time.strftime("%Y%m%d-%H%M%S") + "-" + request.profile
        config = config.model_copy(update=updates)
        # Re-validate after model_copy because update is intentionally low-level.
        config = type(config).model_validate(config.model_dump(mode="json"))
        if not config.run_id:
            raise ApiValidationError("resolved config has no run_id")
        self._validate_run_id(config.run_id)
        resolved = self.config_dir / f"{config.run_id}.yaml"
        write_resolved_config(config, resolved)
        return config, resolved

    def _preflight(self, config_path: Path, run_id: str) -> dict[str, Any]:
        script = self.root / "scripts" / "probabilistic" / "verify_acceleration.py"
        if not script.is_file():
            raise ApiValidationError(f"preflight script not found: {script}")
        output = self.preflight_dir / f"{run_id}.json"
        command = [
            shutil.which("uv") or "uv",
            "run",
            "python",
            str(script),
            "--config",
            str(config_path),
        ]
        completed = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        output.write_text(completed.stdout, encoding="utf-8")
        result = {
            "exit_code": completed.returncode,
            "output": str(output),
            "passed": completed.returncode == 0,
        }
        if completed.returncode != 0:
            raise ApiValidationError("acceleration preflight failed; inspect " + str(output))
        return result

    def start(self, request: StartRunRequest) -> dict[str, Any]:
        with self._lock:
            current = self.current()
            if current and current.get("status") == "RUNNING":
                raise ApiConflictError(
                    f"run already active: {current.get('run_id')} pid={current.get('pid')}"
                )

            config, config_path = self._resolve_config(request)
            run_id = str(config.run_id)
            run_dir = (self.root / config.output / run_id).resolve()
            try:
                run_dir.relative_to(self.root)
            except ValueError as exc:
                raise ApiValidationError("run output escaped project root") from exc

            preflight = None
            if request.preflight and config.native_device == "cuda":
                preflight = self._preflight(config_path, run_id)

            log_path = self.log_dir / f"{run_id}.log"
            log_handle = log_path.open("ab", buffering=0)
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONUNBUFFERED": "1",
                    "OMP_NUM_THREADS": environment.get("OMP_NUM_THREADS", "1"),
                    "OPENBLAS_NUM_THREADS": environment.get("OPENBLAS_NUM_THREADS", "1"),
                    "MKL_NUM_THREADS": environment.get("MKL_NUM_THREADS", "1"),
                    "NUMEXPR_NUM_THREADS": environment.get("NUMEXPR_NUM_THREADS", "1"),
                    "CUDA_VISIBLE_DEVICES": environment.get("CUDA_VISIBLE_DEVICES", "0"),
                    "XLA_PYTHON_CLIENT_PREALLOCATE": environment.get(
                        "XLA_PYTHON_CLIENT_PREALLOCATE", "false"
                    ),
                    "XLA_PYTHON_CLIENT_MEM_FRACTION": environment.get(
                        "XLA_PYTHON_CLIENT_MEM_FRACTION", "0.85"
                    ),
                    "PYTORCH_CUDA_ALLOC_CONF": environment.get(
                        "PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True"
                    ),
                }
            )
            command = [
                shutil.which("uv") or "uv",
                "run",
                "loto3",
                "probabilistic",
                "run",
                "--config",
                str(config_path),
            ]
            process = subprocess.Popen(
                command,
                cwd=self.root,
                env=environment,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            state = {
                "schema_version": 1,
                "status": "RUNNING",
                "run_id": run_id,
                "profile": request.profile,
                "pid": process.pid,
                "process_group_id": process.pid,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "config": str(config_path),
                "source_profile_config": PROFILE_CONFIGS[request.profile],
                "run_dir": str(run_dir),
                "log": str(log_path),
                "command": command,
                "preflight": preflight,
            }
            _atomic_json(self._state_path(run_id), state)
            _atomic_json(self.current_path, state)
            self._processes[run_id] = process
            self._log_handles[run_id] = log_handle
            threading.Thread(
                target=self._watch,
                args=(run_id, process),
                name=f"ppl-api-watch-{run_id}",
                daemon=True,
            ).start()
            return self.status(run_id)

    def _watch(self, run_id: str, process: subprocess.Popen[bytes]) -> None:
        exit_code = process.wait()
        with self._lock:
            state = _read_json(self._state_path(run_id)) or {"run_id": run_id}
            if state.get("stop_requested_at"):
                status = "STOPPED"
            else:
                status = "SUCCEEDED" if exit_code == 0 else "FAILED"
            state.update(
                {
                    "status": status,
                    "exit_code": exit_code,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
            )
            _atomic_json(self._state_path(run_id), state)
            current = _read_json(self.current_path)
            if current and current.get("run_id") == run_id:
                _atomic_json(self.current_path, state)
            handle = self._log_handles.pop(run_id, None)
            if handle is not None:
                handle.close()
            self._processes.pop(run_id, None)

    def stop(self, run_id: str, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._load_state(run_id)
            if state.get("status") != "RUNNING":
                return self.status(run_id)
            pid = int(state.get("process_group_id") or state.get("pid") or 0)
            if not _pid_alive(pid):
                return self.status(run_id)
            chosen = signal.SIGKILL if force else signal.SIGINT
            try:
                os.killpg(pid, chosen)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                raise ApiRunError(f"permission denied stopping process group {pid}") from exc
            state.update(
                {
                    "stop_requested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "stop_signal": chosen.name,
                }
            )
            _atomic_json(self._state_path(run_id), state)
            _atomic_json(self.current_path, state)
            return self.status(run_id)

    def status(self, run_id: str) -> dict[str, Any]:
        state = self._load_state(run_id)
        run_dir = Path(str(state.get("run_dir", "")))
        progress = _read_json(run_dir / "report" / "progress.json")
        summary = _read_json(run_dir / "report" / "summary.json")
        parallelism = _read_json(run_dir / "report" / "parallelism_audit.json")
        return {
            **state,
            "process_alive": _pid_alive(int(state.get("pid") or 0)),
            "progress": progress,
            "summary": summary,
            "parallelism": parallelism,
        }

    def log(self, run_id: str, lines: int = 200) -> str:
        state = self._load_state(run_id)
        return _tail(Path(str(state.get("log", ""))), lines)

    def preflight(self, profile: str) -> dict[str, Any]:
        request = StartRunRequest(profile=profile, preflight=False)
        config, config_path = self._resolve_config(request)
        return self._preflight(config_path, str(config.run_id))

    def test_notifications(self, request: NotificationTestRequest) -> dict[str, Any]:
        command = [
            shutil.which("uv") or "uv",
            "run",
            "python",
            "scripts/probabilistic/test_notifications.py",
        ]
        if request.speech:
            command.extend(["--speech", "--speech-engine", request.speech_engine])
        if request.email:
            command.append("--email")
        completed = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
        return {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "exit_code": completed.returncode,
            "output": completed.stdout,
            "command": command,
        }


def create_app(
    root: str | Path | None = None,
    *,
    manager: ApiRunManager | Any | None = None,
    token: str | None = None,
) -> FastAPI:
    project_root = Path(root or os.environ.get("LOTO_PPL_ROOT", ".")).resolve()
    run_manager = manager or ApiRunManager(project_root)
    expected_token = token if token is not None else os.environ.get("LOTO_PPL_API_TOKEN", "")
    auth_disabled = os.environ.get("LOTO_PPL_API_AUTH_DISABLED", "0") == "1"

    app = FastAPI(
        title="LOTO Probabilistic Execution API",
        version="3.1.0",
        description=(
            "許可済みの確率モデル設定をAPIから開始・停止・監視し、"
            "VOICEVOXによる日本語音声の合成・再生も提供します。"
            "任意シェルコマンドや任意設定パスは受け付けません。"
        ),
    )

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if auth_disabled:
            return
        if not expected_token:
            raise HTTPException(status_code=503, detail="LOTO_PPL_API_TOKEN is not configured")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        supplied = authorization.split(" ", 1)[1]
        if not hmac.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=401, detail="Invalid bearer token")

    @app.get("/health")
    def health() -> dict[str, Any]:
        current = run_manager.current()
        return {
            "status": "ok",
            "root": str(project_root),
            "auth_enabled": not auth_disabled,
            "current_run": current,
        }

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return """<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>LOTO PPL API</title><style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;background:#0b1020;color:#e8eefc}.card{background:#151c31;border:1px solid #33405f;border-radius:12px;padding:1rem;margin:1rem 0}progress{width:100%;height:24px}code,pre{white-space:pre-wrap;word-break:break-word}a{color:#93c5fd}</style></head><body><h1>LOTO Probabilistic API</h1><div class='card'><p>OpenAPI: <a href='/docs'>/docs</a></p><p>API実行にはBearer tokenが必要です。</p></div><div class='card'><h2>現在の進捗</h2><progress id='bar' max='100' value='0'></progress><pre id='out'>Bearer tokenを設定してAPIを呼び出してください。</pre></div><script>const out=document.getElementById('out'),bar=document.getElementById('bar');const token=localStorage.getItem('lotoPplToken')||prompt('Bearer token');if(token)localStorage.setItem('lotoPplToken',token);async function tick(){try{const r=await fetch('/api/v1/runs/current',{headers:{Authorization:'Bearer '+token}});const j=await r.json();const p=j.progress||{};bar.value=p.progress_percent||0;out.textContent=JSON.stringify(j,null,2)}catch(e){out.textContent=String(e)}}tick();setInterval(tick,3000)</script></body></html>"""  # noqa: E501

    @app.get("/api/v1/profiles", dependencies=[Depends(require_token)])
    def profiles() -> list[dict[str, Any]]:
        return run_manager.profiles()

    @app.post("/api/v1/preflight", dependencies=[Depends(require_token)])
    def preflight(request: PreflightRequest) -> dict[str, Any]:
        try:
            return run_manager.preflight(request.profile)
        except ApiValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/runs", status_code=202, dependencies=[Depends(require_token)])
    def start_run(request: StartRunRequest) -> dict[str, Any]:
        try:
            return run_manager.start(request)
        except ApiConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ApiValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ApiRunError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/v1/runs", dependencies=[Depends(require_token)])
    def list_runs(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
        return run_manager.list_runs(limit)

    @app.get("/api/v1/runs/current", dependencies=[Depends(require_token)])
    def current_run() -> dict[str, Any]:
        current = run_manager.current()
        if current is None:
            raise HTTPException(status_code=404, detail="no API run has been started")
        try:
            return run_manager.status(str(current["run_id"]))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="current run state not found") from exc

    @app.get("/api/v1/runs/{run_id}", dependencies=[Depends(require_token)])
    def run_status(run_id: str) -> dict[str, Any]:
        try:
            return run_manager.status(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.post("/api/v1/runs/{run_id}/stop", dependencies=[Depends(require_token)])
    def stop_run(run_id: str, request: StopRunRequest) -> dict[str, Any]:
        try:
            return run_manager.stop(run_id, force=request.force)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except ApiRunError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get(
        "/api/v1/runs/{run_id}/log",
        response_class=PlainTextResponse,
        dependencies=[Depends(require_token)],
    )
    def run_log(run_id: str, lines: int = Query(default=200, ge=1, le=5000)) -> str:
        try:
            return run_manager.log(run_id, lines)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/api/v1/runs/{run_id}/events", dependencies=[Depends(require_token)])
    async def run_events(
        run_id: str,
        interval: float = Query(default=2.0, ge=0.5, le=30.0),
    ) -> StreamingResponse:
        try:
            run_manager.status(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

        async def stream():
            last = ""
            while True:
                try:
                    payload = run_manager.status(run_id)
                except KeyError:
                    yield 'event: error\ndata: {"detail":"run not found"}\n\n'
                    return
                encoded = json.dumps(payload, ensure_ascii=False, default=str)
                if encoded != last:
                    event = "complete" if payload.get("status") in TERMINAL_STATES else "progress"
                    yield f"event: {event}\ndata: {encoded}\n\n"
                    last = encoded
                if payload.get("status") in TERMINAL_STATES:
                    return
                await asyncio.sleep(interval)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/v1/tts/status", dependencies=[Depends(require_token)])
    def tts_status() -> dict[str, Any]:
        try:
            version = _voicevox_get_json("/version")
            return {
                "status": "PASS",
                "engine": "voicevox",
                "url": _voicevox_base_url(),
                "version": version,
            }
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"VOICEVOX unavailable: {type(exc).__name__}: {exc}",
            ) from exc

    @app.get("/api/v1/tts/speakers", dependencies=[Depends(require_token)])
    def tts_speakers() -> Any:
        try:
            return _voicevox_get_json("/speakers", timeout=30)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"VOICEVOX unavailable: {type(exc).__name__}: {exc}",
            ) from exc

    @app.post("/api/v1/tts/synthesize", dependencies=[Depends(require_token)])
    def tts_synthesize(request: TtsRequest) -> Response:
        try:
            audio = _voicevox_synthesize(request)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"VOICEVOX synthesis failed: {type(exc).__name__}: {exc}",
            ) from exc
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'attachment; filename="speech.wav"',
                "X-Voicevox-Speaker": str(request.speaker),
            },
        )

    @app.post("/api/v1/tts/play", dependencies=[Depends(require_token)])
    def tts_play(request: TtsRequest) -> dict[str, Any]:
        try:
            audio = _voicevox_synthesize(request)
            player = _play_wav(audio)
            return {
                "status": "PASS",
                "engine": "voicevox",
                "speaker": request.speaker,
                "speed_scale": request.speed_scale,
                "player": player,
                "text_length": len(request.text),
            }
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"VOICEVOX playback failed: {type(exc).__name__}: {exc}",
            ) from exc

    @app.post("/api/v1/notifications/test", dependencies=[Depends(require_token)])
    def notification_test(request: NotificationTestRequest) -> dict[str, Any]:
        result = run_manager.test_notifications(request)
        if result.get("status") != "PASS":
            raise HTTPException(status_code=502, detail=result)
        return result

    return app


app = create_app()
