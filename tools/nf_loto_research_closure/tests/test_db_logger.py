import json

from src.logging import db_logger


def test_log_run_start_inserts_and_returns_id(monkeypatch, dummy_db):
    # get_connection をダミー接続に差し替え
    monkeypatch.setattr(db_logger, "get_connection", lambda: dummy_db)

    run_id = db_logger.log_run_start(
        table_name="nf_loto_final",
        loto="bingo5",
        unique_ids=["N1", "N2"],
        model_name="AutoTFT",
        backend="optuna",
        horizon=28,
        loss="mse",
        metric="val_loss",
        optimization_config={"backend": "optuna"},
        search_space={"foo": "bar"},
        resource_snapshot={"before": {"cpu": 10}},
        system_info={"host": "test"},
    )

    assert isinstance(run_id, int)
    # INSERT が 1 回実行されていること
    cur = dummy_db.cursor_obj
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "INSERT INTO nf_model_runs" in sql
    assert params["table_name"] == "nf_loto_final"
    assert dummy_db.committed


def test_log_run_end_updates_record(monkeypatch, dummy_db):
    monkeypatch.setattr(db_logger, "get_connection", lambda: dummy_db)

    db_logger.log_run_end(
        run_id=123,
        status="finished",
        metrics={"val_loss": 0.1},
        best_params={"h": 28},
        model_properties={"n_params": 1000},
        resource_after={"after": {"cpu": 20}},
        extra_logs="done",
    )

    cur = dummy_db.cursor_obj
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "UPDATE nf_model_runs" in sql
    assert params["run_id"] == 123
    assert dummy_db.committed


def test_log_run_error_updates_record(monkeypatch, dummy_db):
    monkeypatch.setattr(db_logger, "get_connection", lambda: dummy_db)

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        db_logger.log_run_error(run_id=999, exc=exc)

    cur = dummy_db.cursor_obj
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "UPDATE nf_model_runs" in sql
    assert params["run_id"] == 999
    assert "RuntimeError" in params["error_message"]
    assert dummy_db.committed
