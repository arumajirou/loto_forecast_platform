-- nf_model_runs: モデル実行メタデータ格納テーブル

CREATE TABLE IF NOT EXISTS nf_model_runs (
    id                  BIGSERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    table_name          TEXT NOT NULL,
    loto                TEXT,
    unique_ids          TEXT[],

    model_name          TEXT NOT NULL,
    backend             TEXT NOT NULL,
    horizon             INTEGER NOT NULL,
    loss                TEXT,
    metric              TEXT,

    optimization_config JSONB NOT NULL,
    search_space        JSONB,

    status              TEXT NOT NULL,
    start_time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time            TIMESTAMPTZ,
    duration_seconds    DOUBLE PRECISION,
    metrics             JSONB,
    best_params         JSONB,
    model_properties    JSONB,

    resource_summary    JSONB,
    system_info         JSONB,

    error_message       TEXT,
    traceback           TEXT,
    logs                TEXT,

    mlflow_run_id       TEXT,
    mlflow_experiment   TEXT
);

CREATE OR REPLACE FUNCTION fn_nf_model_runs_set_updated_at()
RETURNS TRIGGER AS $nf$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$nf$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_nf_model_runs_updated_at ON nf_model_runs;

CREATE TRIGGER trg_nf_model_runs_updated_at
BEFORE UPDATE ON nf_model_runs
FOR EACH ROW
EXECUTE FUNCTION fn_nf_model_runs_set_updated_at();
