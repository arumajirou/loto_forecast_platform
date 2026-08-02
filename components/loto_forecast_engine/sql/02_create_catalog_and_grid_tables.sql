CREATE TABLE IF NOT EXISTS catalog.library_catalog (
  library_name TEXT PRIMARY KEY,
  source_path TEXT,
  bundle_kind TEXT,
  row_count INTEGER,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS catalog.module_catalog (
  library_name TEXT NOT NULL,
  module_name TEXT NOT NULL,
  top_group TEXT,
  symbol_count INTEGER NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (library_name, module_name)
);
CREATE TABLE IF NOT EXISTS catalog.symbol_catalog (
  library_name TEXT NOT NULL,
  full_path TEXT NOT NULL,
  module_name TEXT,
  symbol_name TEXT,
  symbol_kind TEXT,
  signature TEXT,
  docstring TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (library_name, full_path)
);
CREATE TABLE IF NOT EXISTS catalog.symbol_param_catalog (
  library_name TEXT NOT NULL,
  full_path TEXT NOT NULL,
  param_name TEXT NOT NULL,
  position_index INTEGER,
  param_kind TEXT,
  required BOOLEAN,
  default_value TEXT,
  annotation TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (library_name, full_path, param_name)
);
