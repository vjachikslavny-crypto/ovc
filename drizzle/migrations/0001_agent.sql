-- Ensure pgvector extension
CREATE EXTENSION IF NOT EXISTS "vector";

-- Adjust note_tags primary key to (note_id, tag)
ALTER TABLE note_tags DROP CONSTRAINT IF EXISTS note_tags_pkey;
ALTER TABLE note_tags DROP COLUMN IF EXISTS id;
ALTER TABLE note_tags
  ADD CONSTRAINT note_tags_pk PRIMARY KEY (note_id, tag);

-- Ensure sources.url is unique
ALTER TABLE sources
  ADD CONSTRAINT sources_url_unique UNIQUE (url);

-- Agent action log for idempotent commits
CREATE TABLE IF NOT EXISTS agent_action_log (
  hash TEXT PRIMARY KEY,
  user_id TEXT,
  action_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
