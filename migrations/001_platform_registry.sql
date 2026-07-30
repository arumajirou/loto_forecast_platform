-- The application creates the same portable schema automatically.
-- This file exists for controlled PostgreSQL deployments and audit review.
CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO schema_migrations(version) VALUES ('001') ON CONFLICT DO NOTHING;
