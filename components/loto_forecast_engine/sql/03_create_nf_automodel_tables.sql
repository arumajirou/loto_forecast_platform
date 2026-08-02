CREATE TABLE IF NOT EXISTS model.model_metric (
  run_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, metric_name)
);
CREATE TABLE IF NOT EXISTS model.forecast (
  run_id TEXT NOT NULL,
  unique_id TEXT NOT NULL,
  ds TIMESTAMPTZ NOT NULL,
  yhat DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS model.exog_contribution (
  run_id TEXT NOT NULL,
  feature_name TEXT NOT NULL,
  importance DOUBLE PRECISION,
  method TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS resources.resource_sample (
  sample_id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  cpu_percent DOUBLE PRECISION,
  mem_percent DOUBLE PRECISION,
  rss_mb DOUBLE PRECISION,
  process_cpu_percent DOUBLE PRECISION,
  system_cpu_percent DOUBLE PRECISION,
  gpu_util DOUBLE PRECISION,
  gpu_mem_mb DOUBLE PRECISION,
  gpu_name TEXT,
  pid INTEGER
);
