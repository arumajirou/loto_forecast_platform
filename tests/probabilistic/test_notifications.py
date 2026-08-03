from types import SimpleNamespace

from loto.probabilistic.notifications import NotificationSettings, progress_message


def test_settings_do_not_store_secret() -> None:
    config = SimpleNamespace(
        speech_enabled=True,
        speech_language="ja",
        speech_engine="auto",
        speech_min_interval_seconds=60,
        voicevox_url="http://127.0.0.1:50021",
        voicevox_speaker=3,
        voicevox_speed_scale=1.15,
        open_jtalk_dictionary=None,
        open_jtalk_voice=None,
        email_enabled=True,
        email_to=["zakumagahiyakesita@gmail.com"],
        email_from="zakumagahiyakesita@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username_env="LOTO_SMTP_USERNAME",
        smtp_password_env="LOTO_SMTP_APP_PASSWORD",
        notification_fail_open=True,
    )
    settings = NotificationSettings.from_config(config)
    assert settings.email_to == ("zakumagahiyakesita@gmail.com",)
    assert settings.speech_engine == "auto"
    assert not hasattr(settings, "smtp_password")


def test_progress_message_contains_eta_and_parallelism() -> None:
    subject, body = progress_message(
        {
            "run_id": "run-1",
            "status": "RUNNING",
            "trials_allowed": 65,
            "completed_allowed": 15,
            "progress_percent": 23.08,
            "status_counts": {"PASS": 12},
            "running_trials": ["model-a"],
            "elapsed_seconds": 100,
            "run_dir": "/tmp/run",
            "eta": {
                "estimated_completion_at": "2026-08-03T18:00:00+09:00",
                "estimated_remaining_text": "2時間",
                "eta_confidence": "medium",
            },
            "parallelism": {"running_total": 4, "outer_workers": 8},
        }
    )
    assert "15/65" in subject
    assert "PASS: 12" in body
    assert "終了予測" in body
    assert "4/8" in body
