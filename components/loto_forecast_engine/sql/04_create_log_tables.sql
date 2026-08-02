CREATE TABLE IF NOT EXISTS log.execution_event_log (
  event_id BIGSERIAL PRIMARY KEY,
  task_id BIGINT,
  run_id TEXT,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  level TEXT NOT NULL DEFAULT 'INFO',
  event_type TEXT NOT NULL,
  message TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS log.run_history (
  history_id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT NOT NULL,
  status TEXT,
  model_name TEXT,
  library_name TEXT,
  adapter_name TEXT,
  grid_id TEXT,
  task_id BIGINT,
  horizon INTEGER,
  dataset_name TEXT,
  log_path TEXT,
  message TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS log.error_event (
  error_id BIGSERIAL PRIMARY KEY,
  run_id TEXT,
  event_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  model_name TEXT,
  stage TEXT,
  error_type TEXT,
  error_message TEXT,
  traceback TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
