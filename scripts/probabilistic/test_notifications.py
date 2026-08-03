from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

from loto.probabilistic.notifications import NotificationManager, NotificationSettings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--speech", action="store_true")
    parser.add_argument("--speech-engine", default="auto")
    parser.add_argument("--voicevox-speaker", type=int, default=3)
    parser.add_argument("--recipient", default="zakumagahiyakesita@gmail.com")
    parser.add_argument(
        "--log",
        default="artifacts/probabilistic-notifications/test-events-v2.jsonl",
    )
    args = parser.parse_args()
    config = SimpleNamespace(
        speech_enabled=args.speech,
        speech_language="ja",
        speech_engine=args.speech_engine,
        speech_min_interval_seconds=0,
        voicevox_url="http://127.0.0.1:50021",
        voicevox_speaker=args.voicevox_speaker,
        voicevox_speed_scale=1.15,
        open_jtalk_dictionary=None,
        open_jtalk_voice=None,
        email_enabled=args.email,
        email_to=[args.recipient],
        email_from=args.recipient,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username_env="LOTO_SMTP_USERNAME",
        smtp_password_env="LOTO_SMTP_APP_PASSWORD",
        notification_fail_open=True,
    )
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    manager = NotificationManager(NotificationSettings.from_config(config), log_path)
    success = True
    if args.speech:
        ok, detail = manager.test_speech_sync(
            "ロト確率モデルの日本語音声通知テストです。"
        )
        print(f"SPEECH_STATUS={'PASS' if ok else 'FAIL'}")
        print(f"SPEECH_DETAIL={detail}")
        success &= ok
    if args.email:
        ok, detail = manager.test_email_sync(
            "[LOTO PPL] メール通知テスト v2",
            "GPU優先並列ランナーのメール通知テストです。",
        )
        print(f"EMAIL_STATUS={'PASS' if ok else 'FAIL'}")
        print(f"EMAIL_DETAIL={detail}")
        success &= ok
    manager.close()
    print(f"LOG={log_path.resolve()}")
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
