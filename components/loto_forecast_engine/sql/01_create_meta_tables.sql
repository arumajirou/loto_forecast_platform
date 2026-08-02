CREATE TABLE IF NOT EXISTS meta.model_run (
  run_id TEXT PRIMARY KEY,
  model_name TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  library_name TEXT,
  adapter_name TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  grid_id TEXT,
  task_id BIGINT,
  log_path TEXT,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS meta.grid_search_definition (
  grid_id TEXT PRIMARY KEY,
  library_name TEXT NOT NULL,
  adapter_name TEXT NOT NULL,
  model_name TEXT NOT NULL,
  horizon INTEGER NOT NULL,
  param_space JSONB NOT NULL DEFAULT '{}'::jsonb,
  exog_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
  run_predict BOOLEAN NOT NULL DEFAULT TRUE,
  run_evaluate BOOLEAN NOT NULL DEFAULT TRUE,
  max_tasks INTEGER,
  note TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.grid_search_task (
  task_id BIGSERIAL PRIMARY KEY,
  grid_id TEXT NOT NULL REFERENCES meta.grid_search_definition(grid_id) ON DELETE CASCADE,
  task_order INTEGER NOT NULL,
  param_values JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending',
  run_id TEXT,
  result JSONB NOT NULL DEFAULT '{}'::jsonb,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  resource_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (grid_id, task_order)
);
