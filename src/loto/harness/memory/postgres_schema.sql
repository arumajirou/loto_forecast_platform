CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS projects (
    project_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    repository TEXT NOT NULL,
    worktree TEXT NOT NULL,
    branch TEXT,
    base_sha TEXT,
    objective TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_events (
    sequence BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    task_id TEXT REFERENCES tasks(task_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    source TEXT NOT NULL,
    commit_sha TEXT,
    branch TEXT,
    protocol_hash TEXT,
    artifact_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_claims (
    sequence BIGSERIAL PRIMARY KEY,
    claim_id UUID NOT NULL UNIQUE,
    project_id BIGINT NOT NULL REFERENCES projects(project_id),
    task_id TEXT REFERENCES tasks(task_id),
    claim_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    source_event_id UUID NOT NULL REFERENCES memory_events(event_id),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    supersedes_claim_id UUID,
    embedding vector,
    embedding_model TEXT,
    embedding_revision TEXT,
    chunker_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memory_events_scope_idx
ON memory_events(project_id, task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS memory_events_payload_gin_idx
ON memory_events USING gin(payload);
CREATE INDEX IF NOT EXISTS memory_claims_text_idx
ON memory_claims USING gin(to_tsvector('simple', statement));
