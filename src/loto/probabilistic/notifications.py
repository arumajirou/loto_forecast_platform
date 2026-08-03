from __future__ import annotations

import json
import os
import shutil
import smtplib
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NotificationSettings:
    speech_enabled: bool = False
    speech_language: str = "ja"
    speech_engine: str = "auto"
    speech_min_interval_seconds: int = 60
    voicevox_url: str = "http://127.0.0.1:50021"
    voicevox_speaker: int = 3
    voicevox_speed_scale: float = 1.15
    open_jtalk_dictionary: str | None = None
    open_jtalk_voice: str | None = None
    email_enabled: bool = False
    email_to: tuple[str, ...] = ()
    email_from: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username_env: str = "LOTO_SMTP_USERNAME"
    smtp_password_env: str = "LOTO_SMTP_APP_PASSWORD"
    notification_fail_open: bool = True

    @classmethod
    def from_config(cls, config: Any) -> NotificationSettings:
        return cls(
            speech_enabled=bool(config.speech_enabled),
            speech_language=str(config.speech_language),
            speech_engine=str(getattr(config, "speech_engine", "auto")),
            speech_min_interval_seconds=int(config.speech_min_interval_seconds),
            voicevox_url=str(getattr(config, "voicevox_url", "http://127.0.0.1:50021")),
            voicevox_speaker=int(getattr(config, "voicevox_speaker", 3)),
            voicevox_speed_scale=float(getattr(config, "voicevox_speed_scale", 1.15)),
            open_jtalk_dictionary=(
                str(config.open_jtalk_dictionary)
                if getattr(config, "open_jtalk_dictionary", None)
                else None
            ),
            open_jtalk_voice=(
                str(config.open_jtalk_voice) if getattr(config, "open_jtalk_voice", None) else None
            ),
            email_enabled=bool(config.email_enabled),
            email_to=tuple(str(value) for value in config.email_to),
            email_from=str(config.email_from) if config.email_from else None,
            smtp_host=str(config.smtp_host),
            smtp_port=int(config.smtp_port),
            smtp_username_env=str(config.smtp_username_env),
            smtp_password_env=str(config.smtp_password_env),
            notification_fail_open=bool(config.notification_fail_open),
        )


class NotificationManager:
    """Non-blocking Japanese speech and SMTP notifications.

    VOICEVOX is preferred for Japanese speech. Open JTalk, speech-dispatcher and
    eSpeak are fail-open fallbacks. SMTP credentials stay in environment
    variables and are never copied into run artifacts.
    """

    def __init__(self, settings: NotificationSettings, log_path: str | Path):
        self.settings = settings
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ppl-notify")
        self._lock = threading.Lock()
        self._last_speech_at = 0.0
        self._futures: set[Future[Any]] = set()

    def _record(self, event: str, status: str, **details: Any) -> None:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "event": event,
            "status": status,
            **details,
        }
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def _submit(self, event: str, function: Any, *args: Any) -> None:
        future = self._executor.submit(self._guarded, event, function, *args)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def _discard_future(self, future: Future[Any]) -> None:
        with self._lock:
            self._futures.discard(future)

    def _guarded(self, event: str, function: Any, *args: Any) -> None:
        try:
            details = function(*args)
            self._record(event, "PASS", **(details if isinstance(details, dict) else {}))
        except Exception as exc:
            self._record(event, "FAIL", error=f"{type(exc).__name__}: {exc}")
            if not self.settings.notification_fail_open:
                raise

    @staticmethod
    def _play_wav(path: Path) -> str:
        candidates = [
            ("paplay", ["paplay", str(path)]),
            ("aplay", ["aplay", "-q", str(path)]),
            ("mpv", ["mpv", "--no-video", "--really-quiet", str(path)]),
            ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)]),
        ]
        for name, command in candidates:
            if shutil.which(name):
                subprocess.run(command, check=True, timeout=120)
                return name
        raise RuntimeError(
            "no WAV player found; install pulseaudio-utils, alsa-utils, mpv, or ffmpeg"
        )

    def _voicevox_available(self) -> bool:
        url = self.settings.voicevox_url.rstrip("/") + "/version"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def _speak_voicevox(self, text: str) -> dict[str, Any]:
        base = self.settings.voicevox_url.rstrip("/")
        speaker = self.settings.voicevox_speaker
        query_url = f"{base}/audio_query?" + urllib.parse.urlencode(
            {"speaker": speaker, "text": text}
        )
        request = urllib.request.Request(query_url, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            query = json.loads(response.read().decode("utf-8"))
        query["speedScale"] = self.settings.voicevox_speed_scale
        body = json.dumps(query, ensure_ascii=False).encode("utf-8")
        synthesis_url = f"{base}/synthesis?" + urllib.parse.urlencode({"speaker": speaker})
        synthesis_request = urllib.request.Request(
            synthesis_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(synthesis_request, timeout=120) as response:
            audio = response.read()
        if len(audio) < 44:
            raise RuntimeError("VOICEVOX returned an invalid WAV payload")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(audio)
            wav_path = Path(handle.name)
        try:
            player = self._play_wav(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)
        return {"engine": "voicevox", "speaker": speaker, "player": player}

    @staticmethod
    def _first_existing(candidates: list[str]) -> str | None:
        return next((value for value in candidates if value and Path(value).exists()), None)

    def _open_jtalk_paths(self) -> tuple[str, str]:
        dictionary = self.settings.open_jtalk_dictionary or self._first_existing(
            [
                "/var/lib/mecab/dic/open-jtalk/naist-jdic",
                "/usr/share/open_jtalk/dic",
                "/usr/local/share/open_jtalk/dic",
            ]
        )
        voice = self.settings.open_jtalk_voice or self._first_existing(
            [
                "/usr/share/hts-voice/mei/mei_normal.htsvoice",
                "/usr/share/hts-voice/mei/mei_happy.htsvoice",
                "/usr/local/share/hts-voice/mei/mei_normal.htsvoice",
            ]
        )
        if not dictionary or not voice:
            raise RuntimeError("Open JTalk dictionary/voice not found")
        return dictionary, voice

    def _speak_open_jtalk(self, text: str) -> dict[str, Any]:
        if not shutil.which("open_jtalk"):
            raise RuntimeError("open_jtalk command not found")
        dictionary, voice = self._open_jtalk_paths()
        with tempfile.TemporaryDirectory(prefix="ppl-open-jtalk-") as temp_dir:
            root = Path(temp_dir)
            input_path = root / "speech.txt"
            wav_path = root / "speech.wav"
            input_path.write_text(text + "\n", encoding="utf-8")
            with input_path.open("r", encoding="utf-8") as source:
                subprocess.run(
                    [
                        "open_jtalk",
                        "-x",
                        dictionary,
                        "-m",
                        voice,
                        "-ow",
                        str(wav_path),
                    ],
                    stdin=source,
                    check=True,
                    timeout=120,
                )
            player = self._play_wav(wav_path)
        return {"engine": "open_jtalk", "voice": voice, "player": player}

    def _speak_spd(self, text: str) -> dict[str, Any]:
        if not shutil.which("spd-say"):
            raise RuntimeError("spd-say command not found")
        subprocess.run(
            ["spd-say", "-w", "-l", self.settings.speech_language, text],
            check=True,
            timeout=120,
        )
        return {"engine": "spd_say"}

    def _speak_espeak(self, text: str) -> dict[str, Any]:
        command = shutil.which("espeak-ng") or shutil.which("espeak")
        if not command:
            raise RuntimeError("espeak-ng/espeak command not found")
        subprocess.run(
            [command, "-v", self.settings.speech_language, text],
            check=True,
            timeout=120,
        )
        return {"engine": Path(command).name}

    def _speech_engines(self) -> list[str]:
        selected = self.settings.speech_engine
        if selected != "auto":
            return [selected]
        return ["voicevox", "open_jtalk", "spd_say", "espeak"]

    @staticmethod
    def _normalize_japanese_speech(text: str) -> str:
        replacements = {
            "PASS": "パス",
            "PARTIAL": "一部成功",
            "FAILED": "失敗",
            "INFERENCE_FAILED": "推論失敗",
            "MODEL_BUILD_FAILED": "モデル構築失敗",
            "POSTERIOR_INVALID": "事後分布不正",
            "GPU": "ジーピーユー",
            "CPU": "シーピーユー",
            "MAE": "平均絶対誤差",
            "MSE": "平均二乗誤差",
            "PPL": "確率モデル",
        }
        output = text
        for source, target in replacements.items():
            output = output.replace(source, target)
        return output.replace("_", " ").replace("__", " ")

    def _speak(self, text: str) -> dict[str, Any]:
        text = self._normalize_japanese_speech(text)
        errors: list[str] = []
        for engine in self._speech_engines():
            try:
                if engine == "voicevox":
                    if not self._voicevox_available():
                        raise RuntimeError(f"VOICEVOX unavailable at {self.settings.voicevox_url}")
                    return self._speak_voicevox(text)
                if engine == "open_jtalk":
                    return self._speak_open_jtalk(text)
                if engine == "spd_say":
                    return self._speak_spd(text)
                if engine == "espeak":
                    return self._speak_espeak(text)
                raise RuntimeError(f"unknown speech engine: {engine}")
            except Exception as exc:
                errors.append(f"{engine}: {type(exc).__name__}: {exc}")
        raise RuntimeError("; ".join(errors))

    def speak(self, text: str, *, force: bool = False) -> None:
        if not self.settings.speech_enabled:
            return
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_speech_at < self.settings.speech_min_interval_seconds:
                return
            self._last_speech_at = now
        self._submit("speech", self._speak, text)

    def test_speech_sync(self, text: str) -> tuple[bool, str]:
        try:
            details = self._speak(text)
            self._record("speech", "PASS", **details)
            return True, json.dumps(details, ensure_ascii=False)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._record("speech", "FAIL", error=error)
            return False, error

    def _credentials(self) -> tuple[str, str]:
        username = os.environ.get(self.settings.smtp_username_env, "").strip()
        raw_password = os.environ.get(self.settings.smtp_password_env, "")
        password = "".join(raw_password.split())
        if not username:
            raise RuntimeError(f"missing environment variable {self.settings.smtp_username_env}")
        if not password:
            raise RuntimeError(f"missing environment variable {self.settings.smtp_password_env}")
        return username, password

    def _send_email(self, subject: str, body: str) -> dict[str, Any]:
        recipients = self.settings.email_to
        if not recipients:
            raise RuntimeError("email_enabled=true but email_to is empty")
        username, password = self._credentials()
        sender = self.settings.email_from or username
        message = EmailMessage()
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
        return {"recipients": list(recipients), "smtp_host": self.settings.smtp_host}

    def email(self, subject: str, body: str) -> None:
        if not self.settings.email_enabled:
            return
        self._submit("email", self._send_email, subject, body)

    def test_email_sync(self, subject: str, body: str) -> tuple[bool, str]:
        try:
            details = self._send_email(subject, body)
            self._record("email", "PASS", **details)
            return True, json.dumps(details, ensure_ascii=False)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._record("email", "FAIL", error=error)
            return False, error

    def close(self, timeout_seconds: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            with self._lock:
                pending = list(self._futures)
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        self._executor.shutdown(wait=False, cancel_futures=False)


def progress_message(progress: dict[str, Any]) -> tuple[str, str]:
    completed = int(progress.get("completed_allowed", 0))
    allowed = int(progress.get("trials_allowed", 0))
    percent = float(progress.get("progress_percent", 0.0))
    passed = int((progress.get("status_counts") or {}).get("PASS", 0))
    non_pass = max(completed - passed, 0)
    remaining = max(allowed - completed, 0)
    best = progress.get("best_model") or {}
    eta = progress.get("eta") or {}
    parallel = progress.get("parallelism") or {}
    gpu = progress.get("gpu") or {}
    best_text = ""
    if best:
        best_text = (
            f"\n暫定最良: {best.get('model_id')}"
            f" / ±1率={best.get('hit_at_1')}"
            f" / MAE={best.get('mae')}"
        )
    gpu_text = ""
    if gpu.get("available") and gpu.get("gpus"):
        first = gpu["gpus"][0]
        gpu_text = (
            f"\nGPU: {first.get('name')} / 使用率={first.get('utilization_percent')}%"
            f" / VRAM={first.get('memory_used_mib')}/{first.get('memory_total_mib')} MiB"
        )
    subject = f"[LOTO PPL] {completed}/{allowed} 完了 ({percent:.1f}%)"
    body = (
        f"実行ID: {progress.get('run_id')}\n"
        f"状態: {progress.get('status')}\n"
        f"完了: {completed}/{allowed} ({percent:.1f}%)\n"
        f"PASS: {passed}\n"
        f"非PASS: {non_pass}\n"
        f"残り: {remaining}\n"
        f"終了予測: {eta.get('estimated_completion_at', '--')}\n"
        f"残り予測: {eta.get('estimated_remaining_text', '--')}\n"
        f"ETA信頼度: {eta.get('eta_confidence', '--')}\n"
        f"並列: {parallel.get('running_total', 0)}/{parallel.get('outer_workers', 0)}\n"
        f"実行中: {', '.join(progress.get('running_trials') or []) or 'なし'}\n"
        f"経過秒: {progress.get('elapsed_seconds')}"
        f"{gpu_text}{best_text}\n"
        f"run_dir: {progress.get('run_dir')}\n"
    )
    return subject, body


__all__ = ["NotificationManager", "NotificationSettings", "progress_message"]
